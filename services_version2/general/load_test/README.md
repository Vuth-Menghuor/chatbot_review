# Load Testing the General Retrieval Service

Two tools to answer: *"How many concurrent users can this service handle?"*

---

## Quick: `concurrency_ramp_test.py`

No Locust needed — pure `asyncio` + `aiohttp`.

```bash
pip install aiohttp

# Baseline — test /health first (cheapest endpoint)
python load_test/concurrency_ramp_test.py \
  --url http://localhost:8005 \
  --endpoint /health \
  --steps 1,5,10,25,50,100,200

# Full pipeline
python load_test/concurrency_ramp_test.py \
  --url http://localhost:8005 \
  --endpoint /retrieval/retrieve \
  --steps 1,5,10,25,50,100,200 \
  --requests-per-user 3
```

The script fires waves of N concurrent virtual users and prints a table:

```
 Users |   Reqs |     RPS |  Fail% |   p50ms |   p95ms |   p99ms |   maxms
--------------------------------------------------------------------------
     1 |      3 |   120.5 |   0.0% |    12.3 |    18.7 |    18.7 |    18.7
    10 |     30 |   245.3 |   0.0% |    45.2 |    89.1 |    95.3 |    95.3
    50 |    150 |   310.7 |   0.0% |   150.4 |   280.9 |   310.2 |   312.5
   100 |    300 |   285.2 |  12.0% |   420.3 |   890.5 |   950.1 |   955.3
```

**How to read:** watch for the step where `Fail%` starts climbing or
`p95ms` jumps sharply (a knee in the curve, not just proportional rise).
That's your practical concurrency ceiling. The script auto-stops when
failure rate crosses `--fail-fast-threshold` (default 20%).

Test `/health` first as a baseline — if that also degrades at similar
concurrency, the bottleneck is the web server / connection handling.
If `/health` stays fast while `/retrieval/retrieve` degrades, the
bottleneck is Qdrant, Gemini, or the CPU-bound reranking logic.

---

## Full-featured: Locust

```bash
pip install locust

# Interactive (live charts in browser)
locust -f load_test/locustfile.py --host http://localhost:8005
# → open http://localhost:8089

# Headless (CI / repeatable runs)
locust -f load_test/locustfile.py --host http://localhost:8005 \
  --users 100 --spawn-rate 10 --run-time 2m --headless \
  --csv=results/run1
```

Locust simulates realistic user behaviour with think-time between requests
and weighted task distribution (5× retrieve, 1× health).
