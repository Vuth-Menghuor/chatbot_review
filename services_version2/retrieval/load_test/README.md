# Testing the Retrieval Service

Two kinds of testing here:

1. **Unit / integration tests** (`../tests/`) — verify the classification
   logic is correct, without needing Qdrant/Redis/Gemini running.
2. **Load / concurrency testing** (this folder) — answers "how many users
   can hit this at once before it falls over?"

---

## 1. Unit + API tests

```bash
cd retrieval
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

- `tests/test_helpers.py` — pure logic: HS-code normalization, cc-range
  parsing, vehicle constraint extraction (fuel/body/drive/assembly/cc),
  hard filtering, lexical scoring, text humanization. No network calls.
- `tests/test_api.py` — hits the actual FastAPI routes via `TestClient`
  with a mocked `RetrievalService`, checking status codes and response
  shape for `/hs-code-candidates`, `/hs-code-ranked`, `/health`, `/`.

**Bugs/quirks these tests caught and documented** (search for
`KNOWN_QUIRK` / `KNOWN_GAP` in `test_helpers.py`):
- `_extract_cc_ranges` on text like `"exceeding 1500cc but not exceeding
  3000cc"` produces an extra spurious unbounded range because the
  standalone "exceeding X cc" regex also matches inside the compound
  phrase. Net effect: cc values *above* the stated upper bound can still
  pass the filter.
- `_derive_vehicle_constraints` only recognizes `4WD`/`4x4`/`AWD`/
  `all-wheel` — the spelled-out `"four-wheel drive"` is not matched.
- The car-model heuristic (used to default `body=suv, drive=4wd` for
  bare model names) requires 2+ digits touching a short token (e.g.
  `RX350`), so single-digit model names like `X5` aren't picked up.
- A failing vector-store call inside `_build_hs_candidate_documents` is
  swallowed (via `asyncio.gather(..., return_exceptions=True)`), so
  `/hs-code-candidates` returns **200 with an empty result set** rather
  than a 500 when the backend is down — worth knowing for monitoring/alerting.

None of these are necessarily wrong for your use case — just now they're
pinned down by tests instead of silently varying behavior.

---

## 2. Load / concurrency testing — "how many users at once?"

Two options, pick whichever fits your workflow. Both need the service
actually running (`uvicorn app.app:app --port 8003` or
`docker compose up`).

### Option A — quick, no extra tooling: `concurrency_ramp_test.py`

```bash
pip install aiohttp
python load_test/concurrency_ramp_test.py \
    --url http://localhost:8003 \
    --endpoint /hs-code-candidates \
    --steps 1,5,10,25,50,100,200,400 \
    --requests-per-user 3
```

This fires waves of N concurrent "virtual users" at the endpoint, one
step at a time, and prints throughput / failure-rate / latency
percentiles per step:

```
 Users |   Reqs |     RPS |  Fail% |   p50ms |   p95ms |   p99ms |   maxms
--------------------------------------------------------------------------
     1 |      3 |   243.1 |   0.0% |     1.8 |     8.6 |     8.6 |     8.6
    10 |     30 |   588.7 |   0.0% |    15.9 |    20.0 |    20.1 |    20.1
    50 |    150 |   620.3 |   0.0% |    67.7 |   100.4 |   109.6 |   110.9
   100 |    300 |   624.3 |   0.0% |   133.8 |   183.4 |   197.9 |   200.6
```

**How to read this:** watch for the step where `Fail%` starts climbing
or `p95ms` jumps sharply relative to the previous step (not just rising
proportionally with load — a sudden knee in the curve). That's your
practical concurrency ceiling. The script also auto-stops once failure
rate crosses `--fail-fast-threshold` (default 20%).

Test `/health` first as a baseline (cheap, no LLM/vector-store work) —
if that also degrades at similar concurrency, the ceiling is coming from
the web server / connection handling, not the classification logic
itself. If `/health` stays fast while `/hs-code-candidates` degrades,
the bottleneck is Qdrant, Gemini, or the CPU-bound scoring logic.

### Option B — full-featured: Locust (`locustfile.py`)

```bash
pip install locust

# Interactive (best for exploring — live charts in browser):
locust -f load_test/locustfile.py --host http://localhost:8003
# open http://localhost:8089, set user count + spawn rate, watch live

# Headless (best for repeatable/scripted runs, CI):
locust -f load_test/locustfile.py --host http://localhost:8003 \
    --users 200 --spawn-rate 20 --run-time 3m --headless \
    --csv=results/run1
```

Locust simulates realistic users (random think-time between requests,
weighted mix of `/hs-code-candidates`, `/hs-code-ranked`, `/health`) and
gives you a live web dashboard plus CSV exports with p50/p95/p99 over
time — better than the ramp script for sustained-load / soak testing,
whereas the ramp script is better for a fast "where's the cliff" check.

### Practical tips for finding your real ceiling

- **Test against Docker Compose, not `--reload` uvicorn** — `--reload`
  and single-worker dev servers behave very differently from production.
  Run `docker compose up -d` first, or set `RETRIEVAL_WORKERS` > 1.
- **Isolate the bottleneck**: run the ramp test against `/health` (near
  zero-cost), then `/hs-code-candidates` with `generate_answer: false`
  (skips the Gemini call), then with `generate_answer: true` (full path
  including the LLM round trip). Comparing these three tells you whether
  Gemini latency, Qdrant, or raw HTTP handling is your limiting factor.
- **Gemini calls are the likely bottleneck** — `GeminiClient.generate_answer`
  runs the (synchronous) `google-genai` SDK call inside `asyncio.to_thread`,
  so throughput there is bounded by Python's thread pool and Gemini's own
  API rate limits, not by `RETRIEVAL_WORKERS`. If most of your load is
  `generate_answer: true` requests, your real ceiling is often "however
  many concurrent Gemini calls your API key/rate-limit tier allows,"
  which the ramp test will surface as failures/timeouts once you hit it.
- **Watch Qdrant/Redis containers too** (`docker stats`) — a shared
  Qdrant instance behind multiple services can become the real ceiling
  even if the retrieval service itself looks fine.