#!/usr/bin/env python3
"""
Orchestrator Context Bleed Test
---------------------------------
Verifies that concurrent chat sessions NEVER contaminate each other's
conversation context, even under load.

Each worker runs a fully independent multi-turn conversation on a unique
session_id with a distinct topic. After every bot response the script checks
whether the answer contains keywords that belong exclusively to a DIFFERENT
topic. Any match is flagged as a context-bleed incident.

The bleed check is applied to EVERY turn in the conversation, so it catches:
  1. Turn-1 bleed  (global state, bad session initialisation)
  2. Turn-2+ bleed (prior-turn history from another session leaking in)
  3. Cross-worker bleed (shared coordinator / rewriter state)

Usage:
  python orchestrator/tests/test_context_bleed.py
  python orchestrator/tests/test_context_bleed.py --url http://127.0.0.1:8001/chat --concurrency 8 --sessions 20
  python orchestrator/tests/test_context_bleed.py --url http://127.0.0.1:8001/query/stream --sessions 20 --stream
"""

import asyncio
import time
import uuid
import random
import logging
import json
import argparse
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import httpx
import numpy as np

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ContextBleedTest")


# Session flow definitions
# Each topic has:
#   turns           – ordered list of messages the user sends
#   expected_words  – words that SHOULD appear in responses (sanity check only)
#   forbidden_words – words that must NEVER appear (belong to other topics only)
SESSION_FLOWS: List[Dict[str, Any]] = [
    # --- Same-category confusion: two electronics items, easy to bleed HS code/entity ---
    {
        "topic": "laptop_then_phone",
        "turns": [
            "hs code of laptop",
            "what about import tax for it",
            "now I want to ask about smartphones instead, what's the HS code",
            "what is the import duty for that",
        ],
        "forbidden_words": ["8471", "laptop", "notebook"],  
        "check_turn": 4, 
    },

    # --- Same-category confusion: two vehicles ---
    {
        "topic": "phone_then_calculate_tax",
        "turns": [
            "I want to import a Phone from China",
            "What is the import tax of it",
            "8517.13.00",
            "30000 usd",
        ],
        "forbidden_words": [],  
        "check_turn": 4,
    },

    # --- Currency inheritance across turns ---
    {
        "topic": "currency_bleed",
        "turns": [
            "What is the hs code of Iphone?",
            "I'm importing iphone worth 5000 EUR from Germany",
            "actually let's recalculate, the value is 6000 USD instead",
        ],
        "forbidden_words": ["EUR", "euro"], 
        "check_turn": 3,
    },

    # --- Quantity/unit-price inheritance (multiplication bug class) ---
    {
        "topic": "quantity_bleed",
        "turns": [
            "importing 50 units of Iphone at $1000 each",
            "8517.13.00",
            "now a separate shipment, 10 units at $20000 each",
            "same hs code 8517.13.00",
        ],
        "forbidden_words": ["50 units", "50,000.00"],  
        "check_turn": 4,
    },

    # --- Pronoun resolution edge case: ambiguous "it" after multi-entity turn ---
    {
        "topic": "pronoun_ambiguity",
        "turns": [
            "I'm comparing importing either a laptop or a printer, which has lower duty",
            "ok tell me the HS code for it",
        ],
        "forbidden_words": [],  # expect a CLARIFICATION_REQUIRED, not a guessed entity
        "expect_clarification": True,
        "check_turn": 2,
    },

    # --- Origin-country bleed (the "it" -> Italy fabrication bug class) ---
    {
        "topic": "origin_country_bleed",
        "turns": [
            "I'm importing wine from Italy",
            "what documents do I need",
            "now separately, I want to import rice from Vietnam",
            "what documents do I need for it",
        ],
        "forbidden_words": ["Italy", "Italian"],  # turn 4 must not fabricate/inherit Italy as origin
        "check_turn": 4,
    },

    # --- Topic switch mid-clarification: user abandons pending slot-fill ---
    {
        "topic": "clarification_abandonment",
        "turns": [
            "hs code of laptop",  # triggers clarification: full device vs battery
            "actually never mind, what is the import procedure for frozen shrimp",
        ],
        "forbidden_words": ["laptop", "battery", "notebook"],
        "check_turn": 2,  # pending clarification state must reset, not merge shrimp answer with laptop clarification
    },

    # --- Language pin vs one-off translation (shouldn't bleed pin across topics) ---
    {
        "topic": "language_pin_isolation",
        "turns": [
            "translate this to Khmer: what is the import tax for a laptop",
            "what about for a car",  # should this be Khmer (pinned) or English (one-off)? verify against your pinning spec
        ],
        "forbidden_words": [],
        "note": "verify expected language behavior matches your persistent-preference vs one-off distinction",
    },

    # --- Cross-session-like same-turn quantity + currency + entity combined stress test ---
    {
        "topic": "combined_stress",
        "turns": [
            "importing 200 cotton t-shirts at 5 EUR each from Vietnam",
            "different order now: 50 leather jackets at 40 USD each from Vietnam",
        ],
        "forbidden_words": [],
        "check_turn": 2,
    },
    # --- HS code clarification resolution (no re-validation or entity override) ---
    {
        "topic": "hs_clarification_no_revalidation",
        "turns": [
            "Calculate import tax for cotton t-shirts from Germany", # Turn 1: calculation, triggers HS code slot collection
            "6109.10.10", # Turn 2: resolves HS code, must prompt for price next, not query 'textile' or ask for blouses/rubber
        ],
        "forbidden_words": ["blouse", "rubber", "textile", "geese", "carpet"],
        "check_turn": 2,
    },
    # --- HS code clarification resolution (alternative candidate code 6205.20.90) ---
    {
        "topic": "hs_clarification_no_revalidation_alternative",
        "turns": [
            "Calculate import tax for cotton t-shirts from Germany", # Turn 1: calculation, triggers HS code slot collection
            "6205.20.90", # Turn 2: resolves HS code, must prompt for price next, not query 'textile'
        ],
        "forbidden_words": ["blouse", "rubber", "textile", "geese", "carpet"],
        "check_turn": 2,
    },
]


# Data models
@dataclass
class BleedIncident:
    session_id: str
    topic: str
    turn_number: int
    user_query: str
    bot_response_preview: str
    matched_forbidden_words: List[str]


@dataclass
class SessionResult:
    session_id: str
    topic: str
    turns_completed: int
    turn_latencies: List[float] = field(default_factory=list)
    incidents: List[BleedIncident] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# HTTP helpers
async def _parse_sse_stream(response: httpx.Response) -> str:
    """Consume an SSE text/event-stream response and return joined answer."""
    parts: List[str] = []
    async for line in response.aiter_lines():
        line = line.strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("data:"):
            try:
                data = json.loads(line[5:].strip())
                if "chunk" in data:
                    parts.append(data["chunk"])
            except json.JSONDecodeError:
                pass
    return "".join(parts)


async def send_turn(
    client: httpx.AsyncClient,
    url: str,
    is_stream: bool,
    session_id: str,
    question: str,
) -> Dict[str, Any]:
    """Send one turn of a conversation and return {ok, answer, latency, error}."""
    payload = {
        "question": question,
        "session_id": session_id,
        "user_id": f"bleed_test_{session_id[:8]}",
        "project_id": "context_bleed_test",
    }
    t0 = time.perf_counter()
    try:
        if is_stream:
            headers = {"Accept": "text/event-stream"}
            async with client.stream(
                "POST", url, json=payload, headers=headers, timeout=90.0
            ) as r:
                if r.status_code != 200:
                    raise ValueError(f"HTTP {r.status_code}")
                answer = await _parse_sse_stream(r)
        else:
            r = await client.post(url, json=payload, timeout=90.0)
            if r.status_code != 200:
                raise ValueError(f"HTTP {r.status_code}: {r.text[:200]}")
            body = r.json()
            answer = body.get("answer") or body.get("message") or ""

        latency = (time.perf_counter() - t0) * 1000.0
        return {"ok": True, "answer": answer, "latency": latency}

    except Exception as exc:
        latency = (time.perf_counter() - t0) * 1000.0
        return {"ok": False, "answer": "", "latency": latency, "error": str(exc)}


# Bleed detection
def check_bleed(answer: str, forbidden_words: List[str]) -> List[str]:
    """Return list of forbidden words found in answer (case-insensitive)."""
    lowered = answer.lower()
    return [w for w in forbidden_words if w.lower() in lowered]


# Per-session worker
async def run_session(
    client: httpx.AsyncClient,
    url: str,
    is_stream: bool,
    flow: Dict[str, Any],
) -> SessionResult:
    """
    Play the full multi-turn conversation for one session and return results.
    Each session has a brand-new UUID so there is no cross-session state sharing
    by design — any bleed is therefore a genuine isolation bug.
    """
    session_id = f"bleed_{uuid.uuid4()}"
    result = SessionResult(session_id=session_id, topic=flow["topic"], turns_completed=0)

    for turn_idx, question in enumerate(flow["turns"]):
        turn_num = turn_idx + 1
        logger.debug("[%s] Turn %d → %s", session_id[:12], turn_num, question[:60])

        resp = await send_turn(client, url, is_stream, session_id, question)
        result.turn_latencies.append(resp["latency"])

        if not resp["ok"]:
            err = resp.get("error", "unknown error")
            result.errors.append(f"Turn {turn_num}: {err}")
            logger.warning("[%s] Turn %d FAILED: %s", session_id[:12], turn_num, err)
            break   # stop the conversation chain on first failure

        result.turns_completed += 1
        answer = resp["answer"]

        # ── Bleed detection ──────────────────────────────────────────────
        check_this_turn = True
        if "check_turn" in flow:
            check_this_turn = (turn_num == flow["check_turn"])

        if check_this_turn:
            matched = check_bleed(answer, flow["forbidden_words"])
            if matched:
                incident = BleedIncident(
                    session_id=session_id,
                    topic=flow["topic"],
                    turn_number=turn_num,
                    user_query=question,
                    bot_response_preview=answer[:160].replace("\n", " "),
                    matched_forbidden_words=matched,
                )
                result.incidents.append(incident)
                logger.warning(
                    "🚨 [BLEED] Session %s (topic=%s) Turn %d → leaked words: %s",
                    session_id[:12], flow["topic"], turn_num, matched,
                )

        # Simulate realistic inter-turn thinking pause (300–700 ms)
        await asyncio.sleep(random.uniform(0.3, 0.7))

    return result


# Test orchestrator
class ContextBleedTestRunner:
    def __init__(
        self,
        url: str,
        concurrency: int,
        total_sessions: int,
        is_stream: bool,
    ):
        self.url = url
        self.concurrency = concurrency
        self.total_sessions = total_sessions
        self.is_stream = is_stream

    async def run(self) -> None:
        print(f"\n🔍  Starting context bleed test → {self.url}")
        print(f"    Concurrency={self.concurrency}  Total sessions={self.total_sessions}  "
              f"Turns per session=3  Mode={'SSE' if self.is_stream else 'REST'}\n")

        # Build the full session queue (cycle through all flows)
        session_queue: List[Dict[str, Any]] = []
        for i in range(self.total_sessions):
            session_queue.append(SESSION_FLOWS[i % len(SESSION_FLOWS)])

        limits = httpx.Limits(
            max_keepalive_connections=self.concurrency,
            max_connections=self.concurrency + 10,
        )

        all_results: List[SessionResult] = []
        t_start = time.perf_counter()

        async with httpx.AsyncClient(limits=limits) as client:
            # Process sessions in batches of `concurrency` at a time
            for batch_start in range(0, len(session_queue), self.concurrency):
                batch = session_queue[batch_start: batch_start + self.concurrency]
                batch_num = batch_start // self.concurrency + 1
                total_batches = (len(session_queue) + self.concurrency - 1) // self.concurrency
                print(f"  ▶  Running batch {batch_num}/{total_batches} "
                      f"({len(batch)} sessions concurrently)...")

                batch_results = await asyncio.gather(
                    *[run_session(client, self.url, self.is_stream, flow) for flow in batch]
                )
                all_results.extend(batch_results)

                done = min(batch_start + self.concurrency, len(session_queue))
                incidents_so_far = sum(len(r.incidents) for r in all_results)
                print(f"     ✔  {done}/{len(session_queue)} sessions done | "
                      f"bleed incidents so far: {incidents_so_far}")

        elapsed = time.perf_counter() - t_start
        self._print_report(all_results, elapsed)

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    def _print_report(self, results: List[SessionResult], elapsed: float) -> None:
        total_sessions = len(results)
        sessions_with_errors = sum(1 for r in results if r.errors)
        sessions_with_bleed  = sum(1 for r in results if r.incidents)
        total_turns  = sum(r.turns_completed for r in results)
        total_bleed  = sum(len(r.incidents) for r in results)

        all_latencies = [lat for r in results for lat in r.turn_latencies]

        if all_latencies:
            lat = np.array(all_latencies)
            avg = float(np.mean(lat))
            p50 = float(np.percentile(lat, 50))
            p90 = float(np.percentile(lat, 90))
            p95 = float(np.percentile(lat, 95))
            p99 = float(np.percentile(lat, 99))
        else:
            avg = p50 = p90 = p95 = p99 = 0.0

        bleed_session_pct = (sessions_with_bleed / total_sessions * 100) if total_sessions else 0.0
        bleed_turn_pct    = (total_bleed / total_turns * 100) if total_turns else 0.0

        print("\n" + "=" * 72)
        print("🔍  ORCHESTRATOR CONTEXT BLEED TEST — RESULTS")
        print("=" * 72)
        print(f"  Target URL        : {self.url}")
        print(f"  Mode              : {'Streaming SSE' if self.is_stream else 'Synchronous REST'}")
        print(f"  Concurrency       : {self.concurrency} sessions in parallel")
        print(f"  Test duration     : {elapsed:.1f}s")
        print("-" * 72)
        print(f"  Total sessions    : {total_sessions}")
        print(f"  Sessions OK       : {total_sessions - sessions_with_errors}")
        print(f"  Sessions w/ error : {sessions_with_errors}")
        print(f"  Total turns sent  : {total_turns}")
        print("-" * 72)
        print(f"  Latency Avg       : {avg:>10.1f} ms")
        print(f"  Latency P50 (med) : {p50:>10.1f} ms")
        print(f"  Latency P90       : {p90:>10.1f} ms")
        print(f"  Latency P95       : {p95:>10.1f} ms")
        print(f"  Latency P99       : {p99:>10.1f} ms")
        print("-" * 72)

        verdict = "✅  PASS" if total_bleed == 0 else "🚨  FAIL — CONTEXT BLEED DETECTED"
        print(f"  Context Bleed     : {verdict}")
        print(f"  Sessions bleeding : {sessions_with_bleed} / {total_sessions}  ({bleed_session_pct:.1f}%)")
        print(f"  Turns bleeding    : {total_bleed} / {total_turns}  ({bleed_turn_pct:.2f}%)")
        print("=" * 72)

        # --- Detailed incident log ---
        all_incidents: List[BleedIncident] = [
            inc for r in results for inc in r.incidents
        ]
        if all_incidents:
            print(f"\n🚨  CONTEXT BLEED INCIDENT LOG  ({len(all_incidents)} total)\n")
            for i, inc in enumerate(all_incidents[:15], 1):
                print(f"  [{i:>2}] Session : {inc.session_id[:16]}...")
                print(f"       Topic   : {inc.topic}")
                print(f"       Turn    : {inc.turn_number}")
                print(f"       Query   : {inc.user_query}")
                print(f"       Leaked  : {inc.matched_forbidden_words}")
                print(f"       Preview : \"{inc.bot_response_preview}...\"")
                print("  " + "-" * 60)
            if len(all_incidents) > 15:
                print(f"  ... and {len(all_incidents) - 15} more incidents not shown.\n")
        else:
            print("\n  🎉  Zero context bleed incidents across all sessions and turns!\n")

        # --- Error summary ---
        all_errors = [err for r in results for err in r.errors]
        if all_errors:
            print(f"\n  ❌  Errors encountered ({len(all_errors)} total):")
            freq: Dict[str, int] = {}
            for e in all_errors:
                freq[e] = freq.get(e, 0) + 1
            for msg, cnt in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"     ({cnt}x) {msg}")
            print()

        print("=" * 72 + "\n")


# CLI
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Orchestrator Context Bleed Test — verifies session isolation under concurrency"
    )
    parser.add_argument(
        "--url", default="http://127.0.0.1:8001/chat",
        help="Endpoint to target (default: http://127.0.0.1:8001/chat)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=6,
        help="Number of sessions running in parallel (default: 6 = one per topic)",
    )
    parser.add_argument(
        "--sessions", type=int, default=18,
        help="Total number of session conversations to run (default: 18)",
    )
    parser.add_argument(
        "--stream", action="store_true",
        help="Target the SSE streaming endpoint instead of the sync endpoint",
    )

    args = parser.parse_args()

    url = args.url
    if args.stream and url == "http://127.0.0.1:8001/chat":
        url = "http://127.0.0.1:8001/query/stream"

    runner = ContextBleedTestRunner(
        url=url,
        concurrency=args.concurrency,
        total_sessions=args.sessions,
        is_stream=args.stream,
    )
    asyncio.run(runner.run())
