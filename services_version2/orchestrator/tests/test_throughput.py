#!/usr/bin/env python3
"""
Orchestrator Throughput Limit Test
------------------------------------
Answers the question: "How many requests can the orchestrator handle per minute?"

Fires a high volume of single-turn requests concurrently to find the practical
throughput ceiling. Uses a rotating pool of short, cacheable questions to keep
the Gemini LLM from being the sole bottleneck, so we can measure the
orchestrator's own routing, validation, and response pipeline.

Usage:
  python orchestrator/tests/test_throughput.py
  python orchestrator/tests/test_throughput.py --url http://127.0.0.1:8001/chat --concurrency 10 --duration 60
  python orchestrator/tests/test_throughput.py --url http://127.0.0.1:8001/query/stream --concurrency 10 --duration 60 --stream
"""

import asyncio
import time
import uuid
import random
import logging
import json
import argparse
import sys
from typing import List, Dict, Any
import httpx
import numpy as np

# Logging
logging.basicConfig(
    level=logging.WARNING,          # Keep output quiet during load run
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ThroughputTest")

# Question pool – short, varied, realistic questions spread across intents.
# A diverse pool avoids Redis cache hits dominating the numbers (which would
# make the orchestrator look faster than it really is under live LLM load).
# NOTE: pool contents/order are unchanged from the original.
QUESTION_POOL: List[str] = [
    # --- General ---
    "What is GDCE?",
    "What services does GDCE provide?",
    "Where is the GDCE headquarters?",
    "How do I import goods into Cambodia?",
    "What documents are required for importing products?",
    "How do I find the HS code for my product?",
    "How is import duty calculated?",
    "Does this product require an import permit?",
    "What items cannot be imported into Cambodia?",
    "How do I import a car into Cambodia?",
    "How do I submit a customs declaration?",
    "How do I appeal a customs decision?",

    # --- HS Code Retrieval (English) ---
    "What is the HS code for a laptop computer?",
    "What is the HS code for a smartphone?",
    "Find the HS code for a men's cotton T-shirt.",
    "What is the HS code for roasted coffee beans?",
    "Find the HS code for a lithium-ion battery used in electric vehicles.",
    "What is the HS code for a passenger car with a 1,500cc petrol engine?",
    "Find the HS code for a plastic water bottle with a capacity of 1 liter.",
    "What is the HS code for a digital camera?",
    "Find the HS code for frozen boneless beef.",
    "What is the HS code for a split-system air conditioner?",

    # --- Calculator (English) ---
    "calculate import tax for hs code 8703.22.00 cif 40000USD from china",
    "calculate import tax for hs code 2710.12.26 cif 393684.59USD DV = 700 net mass 505423kg 675789L from vietnam",
    "calculate import tax for hs code 8703.32.00  cif 13869USD from china with ACFTA DV = 0.00 and DQ = 50%",
    "calculate import tax for hs code 8703.22.00 cif 40000USD from china with ACFTA DV = 0.00 and DQ = 40%",
    "calculate import tax for hs code 8703.33.00  cif 9300USD from china with ACFTA DV = 0.00 and DQ = 40%",
    "calculate import tax for hs code 8703.24.00 cif 10500USD from china with ACFTA DV = 0.00",
    "calculate import tax for hs code 8703.33.00  cif 9180USD from china with no FTA",
    "calculate import tax for hs code 8703.24.00 cif 40000USD from china with ACFTA DV = 0.00",
    "calculate import tax for hs code 8703.33.00 cif 9300USD from china with ACFTA DV = 0.00 and DQ = 40%",

    # --- Trade (English) ---
    "How much did Cambodia import from Vietnam?",
    "What was the total value of exports by air in 2024?",
    "What were the top 10 products exported by Cambodia in 2026?",
    "List the top 5 import partners for sea transport in 2024",
    "Show the monthly trend of exports to Thailand",
    "Show the trend of imports by mode of transport over the last 3 years",
    "Compare imports from Japan vs South Korea in 2024",
    "Compare exports of rice to Vietnam and China from 2024 to 2025",
    "What is the breakdown of imports by transport mode for 2025?",
    "Show the country breakdown of air transport exports in 2024",
    "Monthly growth rate of exports to China in 2025",
    "What was the export growth rate of air transport in 2026 compared to 2024?",
    "What is Cambodia's trade balance with China in 2025?",
    "Show the monthly trade balance trend with the United States in 2025",

    # --- Orchestrator / Full-pipeline (English) ---
    "hi how much tax if i import a car hs 8703.22.00 cif is $10500, from china, ACFTA rate, dv=0",
    "can u calculate tax for 8703.22.00 china cif10500usd acfta dv 0",
    "hs code 8703.22.00, cif 10500 usd, china, acfta, dv=0 — total import tax pls",
    "need tax calc for hs code 8703.24.00, cif $40,000, importing from china",
    "whats the import tax on 8703.32.00 cif 9180 usd coming from china no fta",
    "importing coffee beans from malaysia hs 0901.11.00 cif is only 86.98usd, how much tax would that be",
    "steel parts hs 7308.90.00 from thailand cif 2884.91 usd — tax amount?",
    "import tax pls — hs 8703.24.00, cif=40000usd, china, acfta, dv=0, dq 40%",
    "8703.33.00 from china cif 9300$ dv0 dq40% under acfta how much total tax",
    "china import, hs 8703.22.00, cif $13869, acfta applies, dv=0, dq=50%, what's my total import tax",
    "got a car shipment hs8703.24.00 cif40000usd from China. dv=0 dq=40%. tax?",
    "hs 8703.33.00 cif 9300 usd china acfta dv=0 dq=40 need tax breakdown asap",
    "calculating tax for petroleum import hs 2710.12.26 from vietnam, cif 393684.59 usd, dv=700, net mass 505423kg / 675789L — what's the duty+vat+atp breakdown",
    "vietnam petroleum shipment hs code 2710.12.26 cif393684.59 dv 700 mass505423kg vol675789l need full tax calc",
]

# Category boundaries — describes how QUESTION_POOL is segmented (matches the
# comments above) without altering the pool itself. Used only to tag each
# question index with a category name for the per-category report breakdown.
_CATEGORY_SEGMENTS: List[tuple] = [
    ("General", 12),
    ("HS Code", 10),
    ("Calculator", 9),
    ("Trade", 14),
    ("Orchestrator", 14),
]

CATEGORY_OF_INDEX: List[str] = []
for _name, _count in _CATEGORY_SEGMENTS:
    CATEGORY_OF_INDEX.extend([_name] * _count)

assert len(CATEGORY_OF_INDEX) == len(QUESTION_POOL), (
    f"Category segment counts ({len(CATEGORY_OF_INDEX)}) don't match "
    f"QUESTION_POOL length ({len(QUESTION_POOL)}) — update _CATEGORY_SEGMENTS."
)

CATEGORY_ORDER: List[str] = [name for name, _ in _CATEGORY_SEGMENTS]


def _bar(value: float, max_value: float, width: int = 30) -> str:
    """Render a simple ASCII bar scaled to max_value."""
    if max_value <= 0:
        filled = 0
    else:
        filled = int(round((value / max_value) * width))
        filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


# Throughput runner
class ThroughputTestRunner:
    """
    Hammers the orchestrator endpoint with concurrent single-turn requests
    and reports requests-per-minute, requests-per-second, and full latency
    percentile breakdown, plus a per-category view.
    """

    def __init__(self, url: str, concurrency: int, duration_seconds: int, is_stream: bool):
        self.url = url
        self.concurrency = concurrency
        self.duration_seconds = duration_seconds
        self.is_stream = is_stream

        # -- rolling counters (all workers share these via asyncio single thread)
        self.total_requests: int = 0
        self.success_count: int = 0
        self.failure_count: int = 0
        self.latencies: List[float] = []
        self.errors: List[str] = []
        self.start_time: float = 0.0
        self._rpm_samples: List[float] = []   # requests completed in each 10-s window
        self._window_count: int = 0
        self._window_start: float = 0.0

        # -- per-category counters
        self.category_latencies: Dict[str, List[float]] = {c: [] for c in CATEGORY_ORDER}
        self.category_success: Dict[str, int] = {c: 0 for c in CATEGORY_ORDER}
        self.category_failure: Dict[str, int] = {c: 0 for c in CATEGORY_ORDER}

    # HTTP helpers
    async def _parse_sse_response(self, response: httpx.Response) -> str:
        """Consume an SSE stream and return the full concatenated answer."""
        parts: List[str] = []
        async for line in response.aiter_lines():
            line = line.strip()
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_str = line[5:].strip()
                try:
                    data = json.loads(data_str)
                    if "chunk" in data:
                        parts.append(data["chunk"])
                except json.JSONDecodeError:
                    pass
        return "".join(parts)

    async def _send_request(self, client: httpx.AsyncClient, question: str) -> Dict[str, Any]:
        """Send one request and return latency + success/failure info."""
        payload = {
            "question": question,
            "session_id": f"tput_{uuid.uuid4()}",   # unique session → no locking contention
            "user_id": "throughput_test_user",
            "project_id": "throughput_test",
        }
        t0 = time.perf_counter()
        try:
            if self.is_stream:
                headers = {"Accept": "text/event-stream"}
                async with client.stream(
                    "POST", self.url, json=payload, headers=headers, timeout=90.0
                ) as r:
                    if r.status_code != 200:
                        raise ValueError(f"HTTP {r.status_code}")
                    answer = await self._parse_sse_response(r)
            else:
                r = await client.post(self.url, json=payload, timeout=90.0)
                if r.status_code != 200:
                    raise ValueError(f"HTTP {r.status_code}: {r.text[:200]}")
                answer = r.json().get("answer") or r.json().get("message") or ""

            latency_ms = (time.perf_counter() - t0) * 1000.0
            return {"ok": True, "latency": latency_ms, "answer": answer}

        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return {"ok": False, "latency": latency_ms, "error": str(exc)}

    # Worker
    async def _worker(self, client: httpx.AsyncClient, worker_id: int):
        """Keep firing single requests for the full test duration."""
        while time.perf_counter() - self.start_time < self.duration_seconds:
            idx = random.randrange(len(QUESTION_POOL))
            question = QUESTION_POOL[idx]
            category = CATEGORY_OF_INDEX[idx]

            result = await self._send_request(client, question)

            self.total_requests += 1
            self.latencies.append(result["latency"])
            self.category_latencies[category].append(result["latency"])

            if result["ok"]:
                self.success_count += 1
                self.category_success[category] += 1
            else:
                self.failure_count += 1
                self.category_failure[category] += 1
                err_short = result["error"][:120]
                self.errors.append(f"W{worker_id}: {err_short}")
                if self.failure_count <= 5:
                    logger.warning("Worker %d error: %s", worker_id, result["error"][:200])

    # Progress reporter (prints a live line every 10 seconds)
    async def _progress_reporter(self):
        interval = 10
        prev_count = 0
        await asyncio.sleep(interval)
        while time.perf_counter() - self.start_time < self.duration_seconds:
            elapsed = time.perf_counter() - self.start_time
            delta = self.total_requests - prev_count
            rpm_window = (delta / interval) * 60
            self._rpm_samples.append(rpm_window)
            prev_count = self.total_requests
            print(
                f"  ⏱ [{elapsed:4.0f}s] total={self.total_requests:4d} | "
                f"ok={self.success_count} | fail={self.failure_count} | "
                f"RPM (last {interval}s)={rpm_window:.1f}"
            )
            await asyncio.sleep(interval)

    # Report
    def _print_report(self, elapsed: float):
        rps = self.total_requests / elapsed if elapsed > 0 else 0
        rpm = rps * 60
        success_rate = (self.success_count / self.total_requests * 100) if self.total_requests else 0

        if self.latencies:
            lat = np.array(self.latencies)
            avg  = float(np.mean(lat))
            p50  = float(np.percentile(lat, 50))
            p90  = float(np.percentile(lat, 90))
            p95  = float(np.percentile(lat, 95))
            p99  = float(np.percentile(lat, 99))
            p_min = float(np.min(lat))
            p_max = float(np.max(lat))
        else:
            avg = p50 = p90 = p95 = p99 = p_min = p_max = 0.0

        avg_rpm = float(np.mean(self._rpm_samples)) if self._rpm_samples else rpm

        print("\n" + "=" * 72)
        print("🚀  ORCHESTRATOR THROUGHPUT LIMIT TEST — RESULTS")
        print("=" * 72)
        print(f"  Target URL        : {self.url}")
        print(f"  Mode              : {'Streaming SSE' if self.is_stream else 'Synchronous REST'}")
        print(f"  Concurrent workers: {self.concurrency}")
        print(f"  Test duration     : {elapsed:.1f}s  (target {self.duration_seconds}s)")
        print("-" * 72)
        print(f"  Total requests    : {self.total_requests}")
        print(f"  Successful        : {self.success_count}  ({success_rate:.1f}%)")
        print(f"  Failed            : {self.failure_count}")
        print("-" * 72)
        print(f"  Throughput (overall)                 : {rps:.3f} req/s  |  {rpm:.1f} req/min")
        print(f"  Throughput (avg RPM per 10-s window) : {avg_rpm:.1f} req/min")

        # --- RPM trend over time, visualized ---
        if self._rpm_samples:
            print("-" * 72)
            print("  RPM per 10s window:")
            max_rpm = max(self._rpm_samples) or 1.0
            for i, val in enumerate(self._rpm_samples):
                label = f"{i * 10:>4d}s"
                print(f"    {label} | {_bar(val, max_rpm, 30)} {val:>7.1f}")

        # --- Latency percentile visualization ---
        print("-" * 72)
        print("  Latency distribution (s):")
        max_lat = p_max or 1.0
        for label, val in [
            ("Min", p_min), ("Avg", avg), ("P50", p50),
            ("P90", p90), ("P95", p95), ("P99", p99), ("Max", p_max),
        ]:
            print(f"    {label:>4} | {_bar(val, max_lat, 30)} {val / 1000.0:>9.2f} s")

        # --- Per-category breakdown ---
        print("-" * 72)
        print("  Breakdown by question category:")
        header = f"    {'Category':<14}{'Count':>7}{'Success%':>10}{'AvgS':>9}{'P95S':>9}{'RPM':>8}"
        print(header)
        print("    " + "-" * (len(header) - 4))
        for cat in CATEGORY_ORDER:
            cat_lats = self.category_latencies[cat]
            cat_total = self.category_success[cat] + self.category_failure[cat]
            if not cat_total:
                print(f"    {cat:<14}{0:>7}{'--':>10}{'--':>9}{'--':>9}{0.0:>8.1f}")
                continue
            cat_arr = np.array(cat_lats)
            cat_avg = float(np.mean(cat_arr)) / 1000.0
            cat_p95 = float(np.percentile(cat_arr, 95)) / 1000.0
            cat_success_rate = (self.category_success[cat] / cat_total * 100)
            cat_rpm = (cat_total / elapsed) * 60 if elapsed > 0 else 0.0
            print(
                f"    {cat:<14}{cat_total:>7}{cat_success_rate:>9.1f}%"
                f"{cat_avg:>9.2f}{cat_p95:>9.2f}{cat_rpm:>8.1f}"
            )
        print("-" * 72)

        if self.errors:
            print(f"\n  ❌ Top errors (showing up to 5):")
            freq: Dict[str, int] = {}
            for e in self.errors:
                freq[e] = freq.get(e, 0) + 1
            for msg, cnt in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"     ({cnt}x) {msg}")
        else:
            print("\n  ✅  Zero failures during the test run.")

        print("=" * 72 + "\n")

    # Entry point
    async def run(self):
        print(f"\n🔥  Starting throughput test → {self.url}")
        print(f"    Concurrency={self.concurrency}  Duration={self.duration_seconds}s  "
              f"Mode={'SSE' if self.is_stream else 'REST'}\n")

        limits = httpx.Limits(
            max_keepalive_connections=self.concurrency,
            max_connections=self.concurrency + 10,
        )
        self.start_time = time.perf_counter()

        async with httpx.AsyncClient(limits=limits) as client:
            tasks = [self._worker(client, i) for i in range(self.concurrency)]
            tasks.append(self._progress_reporter())
            await asyncio.gather(*tasks)

        elapsed = time.perf_counter() - self.start_time
        self._print_report(elapsed)


# CLI
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Orchestrator Throughput Limit Test — measures max RPM capacity"
    )
    parser.add_argument(
        "--url", default="http://127.0.0.1:8001/chat",
        help="Endpoint to target (default: http://127.0.0.1:8001/chat)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=5,
        help="Number of concurrent workers (default: 5)",
    )
    parser.add_argument(
        "--duration", type=int, default=60,
        help="Test duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--stream", action="store_true",
        help="Target the SSE streaming endpoint instead of the sync endpoint",
    )

    args = parser.parse_args()

    url = args.url
    if args.stream and url == "http://127.0.0.1:8001/chat":
        url = "http://127.0.0.1:8001/query/stream"

    runner = ThroughputTestRunner(
        url=url,
        concurrency=args.concurrency,
        duration_seconds=args.duration,
        is_stream=args.stream,
    )
    asyncio.run(runner.run())