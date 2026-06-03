# Circuit Breaker Testing Guide

## Overview

The GDCE ChatBot implements the **Circuit Breaker Pattern** for resilient service communication. This guide explains the two types of tests and why they measure different things.

## Two Testing Approaches

### 1. CURL Test (HTTP Level)

**File:** `CURL_TEST_CIRCUIT_BREAKER_SAFE.ps1`

```bash
powershell -ExecutionPolicy Bypass -File .\CURL_TEST_CIRCUIT_BREAKER_SAFE.ps1
```

**What it tests:**

- Direct HTTP requests to services
- Service availability/health
- HTTP timeout and retry behavior
- What happens when services are down

**Expected Results:**

- ✅ Test 1: All requests succeed (services up)
- ✅ Test 2: All 10 requests fail with ~2000ms each (HTTP timeout)
- ⚠️ Cannot demonstrate circuit breaker fast-fail

**Why it can't show circuit breaker behavior:**

- Curl makes direct HTTP requests
- Circuit breaker is inside Python `ServiceClient` class
- Curl bypasses the circuit breaker entirely
- Each request independently times out at HTTP level

**Example Output:**

```
Request 1 : FAILED 2004ms (Retry/Backoff)
Request 2 : FAILED 2012ms (Retry/Backoff)
...
Request 10 : FAILED 2002ms (Retry/Backoff)
```

---

### 2. Python Test (Application Level) ⭐ AUTHORITATIVE

**File:** `test_circuit_breaker_python.py`

```bash
python test_circuit_breaker_python.py
```

**What it tests:**

- Actual `CircuitBreaker` class behavior
- State machine transitions (CLOSED → OPEN → HALF_OPEN)
- Failure threshold detection (5 consecutive failures)
- **Fast-fail response when circuit is OPEN**
- Recovery timeout (60 seconds)
- Probe requests in HALF_OPEN state

**Expected Results:**

- ✅ Requests 1-5: ~3300ms each (with retries)
- ✅ Requests 6-15: <1ms each (fast-fail, NO retries)
- ✅ Circuit state transitions logged
- ✅ Proper fast-fail behavior demonstrated

**Example Output:**

```
Request  1 :  3351.7ms [RETRY]     CLOSED     - FAILED (ConnectTimeout)
Request  2 :  3362.9ms [RETRY]     CLOSED     - FAILED (ConnectTimeout)
Request  3 :  3342.6ms [RETRY]     CLOSED     - FAILED (ConnectTimeout)
Request  4 :  3354.8ms [RETRY]     CLOSED     - FAILED (ConnectTimeout)
Request  5 :  3346.4ms [RETRY]     OPEN       - FAILED (ConnectTimeout)
Request  6 :     0.0ms [FAST-FAIL] OPEN       - FAILED (Exception)
Request  7 :     0.0ms [FAST-FAIL] OPEN       - FAILED (Exception)
...
Request 15 :     1.0ms [FAST-FAIL] OPEN       - FAILED (Exception)

Circuit Breaker Final State:
  State: OPEN
  Failure Count: 5
  Success Count: 0
```

---

## Circuit Breaker Implementation

**Location:** `services_version2/orchestrator_version2/infrastructure/clients.py`

### Key Classes

```python
class CircuitBreakerState(Enum):
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Failing fast, blocking requests
    HALF_OPEN = "half_open"    # Testing recovery

class CircuitBreaker:
    """Implements the circuit breaker pattern"""
    - Tracks consecutive failures
    - Opens after 5 failures
    - Fails fast when OPEN (<1ms)
    - Enters HALF_OPEN after 60s
    - Tests recovery with probe requests
    - Transitions back to CLOSED on success

class HttpxServiceClient:
    """Service client with integrated circuit breaker"""
    - Uses CircuitBreaker for resilience
    - Retries transient failures (100ms, 200ms, 400ms backoff)
    - Fast-fails when circuit is OPEN
```

### State Transitions

```
    Normal Operation
          ↓
    ┌─────────────┐
    │   CLOSED    │  ← Accepting all requests
    │ (5 failures)│
    └──────┬──────┘
           │
           ↓ Failure threshold reached
    ┌─────────────┐
    │    OPEN     │  ← Rejecting all requests (<1ms)
    │ (60s wait)  │
    └──────┬──────┘
           │
           ↓ Timeout reached
    ┌─────────────────────┐
    │   HALF_OPEN         │  ← Testing recovery
    │ (probe request)     │
    └──────┬──────────┬───┘
           │          │
     SUCCESS (0)  FAILURE (1)
           │          │
           ↓          ↓
       CLOSED ←──── OPEN
```

---

## Configuration

Default Circuit Breaker Configuration:

```python
CircuitBreakerConfig(
    failure_threshold=5,           # Open after 5 failures
    recovery_timeout_sec=60,       # Wait 60s before probing
    half_open_max_calls=2,         # Max 2 calls in HALF_OPEN
    name="CircuitBreaker"
)
```

Default Retry Configuration:

```python
RetryConfig(
    max_retries=3,                 # 3 retry attempts
    initial_backoff_ms=100,        # Start at 100ms
    max_backoff_ms=10000,          # Cap at 10s
    exponential_base=2.0,          # 2x multiplier
    jitter=True                    # Add 10% random jitter
)
```

---

## When to Use Each Test

| Test                   | When                | Purpose                                 |
| ---------------------- | ------------------- | --------------------------------------- |
| **CURL Test**          | Daily/Sanity checks | Verify services are up and responding   |
| **Python Test**        | Development/Review  | Validate circuit breaker implementation |
| **Production Metrics** | Runtime monitoring  | Track state transitions and failures    |

---

## Recommended Testing Workflow

1. **Start all services**

   ```bash
   cd service_scripts
   powershell -ExecutionPolicy Bypass -File .\start_all_v2.ps1
   ```

2. **Run CURL health check** (quick sanity check)

   ```bash
   powershell -ExecutionPolicy Bypass -File .\CURL_TEST_CIRCUIT_BREAKER_SAFE.ps1
   ```

3. **Run Python circuit breaker test** (comprehensive test)

   ```bash
   python test_circuit_breaker_python.py
   ```

4. **Check logs** for circuit breaker state transitions
   ```bash
   # Monitor in production
   tail -f logs/orchestrator.log | grep CircuitBreaker
   ```

---

## Troubleshooting

### Issue: CURL test shows ~2000ms for all requests

**Reason:** Curl makes direct HTTP calls, each independently times out at HTTP level
**Solution:** Run Python test instead to see actual circuit breaker behavior

### Issue: Python test not showing fast-fails

**Reason:** Circuit breaker not initialized properly
**Solution:** Verify `CircuitBreakerConfig` is being passed to client

### Issue: Circuit not opening after 5 failures

**Reason:** Failures may be resetting before reaching threshold
**Solution:** Check `_on_success()` is only called on actual success, not retries

---

## Next Steps

- ✅ Circuit Breaker pattern: **IMPLEMENTED**
- ✅ Retry logic: **IMPLEMENTED**
- ⏳ Phase 2: Observability (Prometheus metrics, structured logging)
- ⏳ Phase 3: Admin endpoints (circuit breaker control, metrics API)

---

## References

- Implementation: [clients.py](services_version2/orchestrator_version2/infrastructure/clients.py)
- Test: [test_circuit_breaker_python.py](test_circuit_breaker_python.py)
- Architecture: [ORCHESTRATOR_ROADMAP.md](docs/01_system_architecture.md)

---

**Last Updated:** April 20, 2026  
**Status:** ✅ Phase 1 Complete (Stability + Resilience)
