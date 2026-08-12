"""
Locust load test for the Retrieval Service (port 8003).

Simulates many concurrent "users" hammering /hs-code-candidates and
/hs-code-ranked so you can see how many concurrent users the service
holds up under before latency/error rate degrade.

INSTALL:
    pip install locust

RUN (interactive web UI — best for exploring):
    locust -f locustfile.py --host http://localhost:8003
    # then open http://localhost:8089 and set number of users + spawn rate

RUN (headless — best for CI / scripted runs):
    locust -f locustfile.py --host http://localhost:8003 \
        --users 100 --spawn-rate 10 --run-time 2m --headless \
        --csv=results/run1

    --users        total concurrent simulated users at peak
    --spawn-rate   how many new users to start per second (ramp speed)
    --run-time     how long to sustain peak load
    --csv=PREFIX   writes PREFIX_stats.csv, PREFIX_stats_history.csv etc,
                   which is the easiest way to see p50/p95/p99 latency
                   and failure rate over time.

FINDING YOUR MAX CONCURRENT USERS:
    Run headless a few times doubling --users each time (10, 25, 50, 100,
    200, 400...) and watch the "Failure %" and p95 response time in the
    generated *_stats.csv (or the live web UI). The point where failure
    rate starts climbing or p95 latency spikes sharply is your practical
    concurrency ceiling. The /health endpoint is included as a lightweight
    baseline so you can separate "web server / networking" limits from
    "classification logic" limits.
"""

import random
from locust import HttpUser, task, between, events

# Realistic sample queries — mix of specific and generic to exercise both
# the fast-path (specific, gets hard-filtered) and slow-path (generic,
# falls through to semantic search + LLM ranking) branches.
SAMPLE_QUERIES = [
    "BMW M8 Competition",
    "diesel pickup truck 2500cc CBU",
    "cotton fabric",
    "iPhone 14 Pro Max",
    "Toyota Hilux 4WD diesel CKD",
    "leather handbag",
    "electric vehicle SUV",
    "laptop computer",
    "rice, milled",
    "steel pipes",
    "car",
    "phone",
]


class RetrievalUser(HttpUser):
    # Random think-time between requests, per simulated user, so traffic
    # isn't perfectly synchronized. Tune this to mimic real usage patterns.
    wait_time = between(1, 3)

    @task(5)
    def hs_code_candidates(self):
        query = random.choice(SAMPLE_QUERIES)
        with self.client.post(
            "/hs-code-candidates",
            json={"query": query, "top_k": 10, "generate_answer": True},
            name="/hs-code-candidates",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"status={resp.status_code}")

    @task(3)
    def hs_code_ranked(self):
        query = random.choice(SAMPLE_QUERIES)
        with self.client.post(
            "/hs-code-ranked",
            json={"query": query, "generate_answer": True},
            name="/hs-code-ranked",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"status={resp.status_code}")

    @task(1)
    def health(self):
        with self.client.get("/health", name="/health", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"status={resp.status_code}")


@events.quitting.add_listener
def _print_summary(environment, **kwargs):
    stats = environment.stats.total
    print("\n=== Load test summary ===")
    print(f"Requests: {stats.num_requests}  Failures: {stats.num_failures}")
    if stats.num_requests:
        print(f"Failure rate: {100 * stats.num_failures / stats.num_requests:.2f}%")
    print(f"Median: {stats.median_response_time}ms  p95: {stats.get_response_time_percentile(0.95)}ms  p99: {stats.get_response_time_percentile(0.99)}ms")