"""
Locust load test for the General Retrieval Service (port 8005).

Simulates many concurrent "users" hitting ``/retrieval/retrieve`` so you
can see how many concurrent users the service holds up under before
latency / error rate degrade.

Usage
-----
    pip install locust

    # Interactive web UI (best for exploring):
    locust -f locustfile.py --host http://localhost:8005
    # → open http://localhost:8089

    # Headless (best for CI / scripted runs):
    locust -f locustfile.py --host http://localhost:8005 \
        --users 100 --spawn-rate 10 --run-time 2m --headless \
        --csv=results/run1

Finding Your Max Concurrent Users
---------------------------------
Run headless a few times doubling ``--users`` each time (10, 25, 50, 100,
200, 400...) and watch the "Failure %" and p95 response time in the
generated ``*_stats.csv`` (or the live web UI). The point where failure
rate starts climbing or p95 latency spikes sharply is your practical
concurrency ceiling.

The ``/health`` endpoint is included as a lightweight baseline so you can
separate "web server / networking" limits from "retrieval logic" limits.
"""

import random
from locust import HttpUser, task, between, events

# Realistic sample queries — mix of procedural, definition, and policy
# questions the general service would typically handle.
SAMPLE_QUERIES = [
    "What documents do I need to import goods into Cambodia?",
    "How is customs duty calculated?",
    "What is the CIF value?",
    "VAT on imported goods",
    "Customs clearance procedure",
    "ATIGA preferential tariff rates",
    "How to appeal a customs valuation?",
    "What is a bonded warehouse?",
    "Temporary import procedures",
    "Certificate of origin requirements",
    "import",
    "document",
]


class GeneralUser(HttpUser):
    """
    Simulated user for the general retrieval service.

    Weighted tasks: 5× retrieve, 1× health check. Random think time
    between 1-3 seconds per simulated user to mimic real usage patterns.
    """
    wait_time = between(1, 3)

    @task(5)
    def retrieve(self):
        """Hammer the main retrieval endpoint with realistic queries."""
        query = random.choice(SAMPLE_QUERIES)
        with self.client.post(
            "/retrieval/retrieve",
            json={
                "query": query,
                "top_k": 10,
                "generate_answer": True,
                "require_period_for_trade": False,
            },
            name="/retrieval/retrieve",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"status={resp.status_code}")

    @task(1)
    def health(self):
        """Lightweight health-check baseline."""
        with self.client.get("/health", name="/health", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"status={resp.status_code}")


@events.quitting.add_listener
def _print_summary(environment, **kwargs):
    """Print a concise summary when the Locust run finishes."""
    stats = environment.stats.total
    print("\n=== Load test summary ===")
    print(f"Requests: {stats.num_requests}  Failures: {stats.num_failures}")
    if stats.num_requests:
        print(f"Failure rate: {stats.num_failures / stats.num_requests * 100:.1f}%")
        print(f"Avg response: {stats.avg_response_time:.0f} ms")
        print(f"p50: {stats.get_response_time_percentile(0.5):.0f} ms")
        print(f"p95: {stats.get_response_time_percentile(0.95):.0f} ms")
        print(f"p99: {stats.get_response_time_percentile(0.99):.0f} ms")
    print("===========================\n")
