#!/usr/bin/env python3
"""
Standalone concurrency ramp test for the General Retrieval Service.

No Locust needed — pure asyncio + aiohttp. Fires increasing waves of
concurrent requests (e.g. 1, 5, 10, 25, 50, 100, 200...) against the
``/retrieval/retrieve`` endpoint and reports success rate + latency
percentiles per wave, so you can see exactly where the service starts
to degrade or fail.

Usage
-----
    python load_test/concurrency_ramp_test.py --url http://localhost:8005 --endpoint /retrieval/retrieve
    python load_test/concurrency_ramp_test.py --url http://localhost:8005 --endpoint /health
    python load_test/concurrency_ramp_test.py --url http://localhost:8005 --endpoint /retrieval/retrieve \
        --steps 1,5,10,25,50,100,200 --requests-per-user 3

Options
-------
--url                   Base URL of the running service (default: http://localhost:8005)
--endpoint              Which endpoint to test (/health, /retrieval/retrieve)
--steps                 Comma-separated concurrency levels to test, in order
--requests-per-user     How many sequential requests each simulated user fires
--timeout               Per-request timeout in seconds (default: 30)
--fail-fast-threshold   Stop ramping once failure rate exceeds this (0-1), default 0.2
--json-out              Optional path to write full results as JSON
"""

import argparse
import asyncio
import statistics
import time
import json
import sys

try:
    import aiohttp
except ImportError:
    print("Missing dependency. Install with: pip install aiohttp", file=sys.stderr)
    sys.exit(1)


SAMPLE_QUERIES = [
    "What documents do I need to import goods into Cambodia?",
    "How is customs duty calculated?",
    "What is the CIF value?",
    "VAT on imported goods",
    "Customs clearance procedure",
    "ATIGA preferential tariff",
    "import",
    "document",
]


def build_request(endpoint: str, i: int):
    """Return (method, path, json_body) for the given endpoint."""
    if endpoint == "/health" or endpoint == "/":
        return "GET", endpoint, None
    query = SAMPLE_QUERIES[i % len(SAMPLE_QUERIES)]
    if endpoint == "/retrieval/retrieve":
        return "POST", endpoint, {
            "query": query,
            "top_k": 10,
            "generate_answer": True,
            "require_period_for_trade": False,
        }
    # Generic fallback: treat as POST with a query body.
    return "POST", endpoint, {"query": query}


async def fire_one(session, base_url, endpoint, idx, timeout):
    """Fire a single HTTP request and return latency + status."""
    method, path, body = build_request(endpoint, idx)
    start = time.perf_counter()
    try:
        async with session.request(
            method, base_url + path, json=body,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            await resp.read()
            elapsed = time.perf_counter() - start
            return {"ok": resp.status == 200, "status": resp.status, "latency": elapsed}
    except asyncio.TimeoutError:
        return {"ok": False, "status": "timeout", "latency": time.perf_counter() - start}
    except Exception as exc:
        return {"ok": False, "status": f"error:{type(exc).__name__}", "latency": time.perf_counter() - start}


async def simulate_user(session, base_url, endpoint, requests_per_user, timeout, results, user_idx):
    """Simulate one virtual user firing sequential requests."""
    for r in range(requests_per_user):
        res = await fire_one(session, base_url, endpoint, user_idx * requests_per_user + r, timeout)
        results.append(res)


async def run_step(base_url, endpoint, concurrency, requests_per_user, timeout):
    """Run a single concurrency step and collect results."""
    connector = aiohttp.TCPConnector(limit=0)  # no artificial client-side cap
    results = []
    async with aiohttp.ClientSession(connector=connector) as session:
        start = time.perf_counter()
        tasks = [
            simulate_user(session, base_url, endpoint, requests_per_user, timeout, results, u)
            for u in range(concurrency)
        ]
        await asyncio.gather(*tasks)
        wall_time = time.perf_counter() - start
    return results, wall_time


def summarize(results, concurrency, wall_time):
    """Compute summary statistics for a concurrency step."""
    total = len(results)
    failures = [r for r in results if not r["ok"]]
    latencies = sorted(r["latency"] for r in results)

    def pct(p):
        if not latencies:
            return 0.0
        k = min(len(latencies) - 1, int(len(latencies) * p))
        return latencies[k]

    status_counts = {}
    for r in results:
        status_counts[str(r["status"])] = status_counts.get(str(r["status"]), 0) + 1

    return {
        "concurrency": concurrency,
        "total_requests": total,
        "failures": len(failures),
        "failure_rate": (len(failures) / total) if total else 0.0,
        "throughput_rps": total / wall_time if wall_time > 0 else 0.0,
        "wall_time_s": round(wall_time, 3),
        "p50_ms": round(pct(0.50) * 1000, 1),
        "p95_ms": round(pct(0.95) * 1000, 1),
        "p99_ms": round(pct(0.99) * 1000, 1),
        "max_ms": round((latencies[-1] if latencies else 0) * 1000, 1),
        "status_counts": status_counts,
    }


async def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", default="http://localhost:8005", help="Base URL of the service")
    parser.add_argument("--endpoint", default="/health", help="Endpoint to test")
    parser.add_argument("--steps", default="1,5,10,25,50,100,200", help="Comma-separated concurrency levels")
    parser.add_argument("--requests-per-user", type=int, default=1, help="Sequential requests per virtual user")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout (s)")
    parser.add_argument("--fail-fast-threshold", type=float, default=0.2, help="Stop ramping above this failure rate (0-1)")
    parser.add_argument("--json-out", default=None, help="Optional path to write full results as JSON")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    steps = [int(s.strip()) for s in args.steps.split(",") if s.strip()]

    print(f"Target: {base_url}{args.endpoint}")
    print(f"Steps (concurrent users): {steps}")
    print(f"Requests per user per step: {args.requests_per_user}\n")

    header = f"{'Users':>6} | {'Reqs':>6} | {'RPS':>7} | {'Fail%':>6} | {'p50ms':>7} | {'p95ms':>7} | {'p99ms':>7} | {'maxms':>7}"
    print(header)
    print("-" * len(header))

    all_summaries = []
    for concurrency in steps:
        results, wall_time = await run_step(
            base_url, args.endpoint, concurrency, args.requests_per_user, args.timeout,
        )
        summary = summarize(results, concurrency, wall_time)
        all_summaries.append(summary)

        print(
            f"{summary['concurrency']:>6} | {summary['total_requests']:>6} | "
            f"{summary['throughput_rps']:>7.1f} | {summary['failure_rate']*100:>5.1f}% | "
            f"{summary['p50_ms']:>7.1f} | {summary['p95_ms']:>7.1f} | {summary['p99_ms']:>7.1f} | {summary['max_ms']:>7.1f}"
        )

        if summary["failure_rate"] > args.fail_fast_threshold:
            print(
                f"\nFailure rate {summary['failure_rate']*100:.1f}% exceeded threshold "
                f"({args.fail_fast_threshold*100:.0f}%) at {concurrency} concurrent users — stopping ramp."
            )
            print(f"Practical concurrency ceiling looks to be just below {concurrency} users.")
            break
    else:
        print(
            f"\nAll steps completed under the {args.fail_fast_threshold*100:.0f}% failure threshold — "
            f"try higher --steps values to keep probing further."
        )

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(all_summaries, f, indent=2)
        print(f"\nFull results written to {args.json_out}")


if __name__ == "__main__":
    asyncio.run(main())
