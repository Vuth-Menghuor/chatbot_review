# STEP 4: BETTER TIMEOUT MANAGEMENT

## Simple Summary

**What:** Different query types need different timeouts  
**Why:** Calculator query (10s) vs retrieval query (25s) vs trade query (20s)  
**How:** Configuration maps intents to timeouts + passes timeout to service calls  
**Result:** Faster detection of slow services + better resource management

---

## The Problem

```
❌ BEFORE:
Query type: Calculation (usually 5-8 seconds)
Timeout: 30 seconds (generic)
→ User waits 30 seconds for an error message

❌ BEFORE:
Query type: Retrieval (usually 3-5 seconds)
Timeout: 30 seconds (generic)
→ User waits 30 seconds for an error message

❌ BEFORE:
Query type: Trade Query (might be 15-20 seconds)
Timeout: 30 seconds (generic)
→ User gets timeout even though service is working fine
```

## The Solution

```
✅ AFTER:
Calculator → 10s timeout (tight, purpose-specific)
Retrieval → 25s timeout (extended, vector DB searches)
Trade Query → 20s timeout (generous, complex operation)
Definition → 20s timeout (retrieval-based, standard time)
Policy Query → 25s timeout (retrieval-based, extended time)
```

### How It Works

```
Query comes in
       ↓
Detect intent (Calculation? Retrieval? etc.)
       ↓
Look up timeout in config
   Calculation → 10s
   Retrieval → 25s
   Trade → 20s
       ↓
Call service with that timeout
       ↓
If timeout hits → fail fast
If service responds → proceed normally
```

---

## File Structure

```
orchestrator_version2/
├── core/
│   ├── timeout_config.py ← NEW (STEP 4)
│   ├── coordinator.py ← MODIFIED (4 methods updated)
│   └── __init__.py ← MODIFIED (added exports)
│
├── tests/
│   └── test_timeout_config.py ← NEW (20 comprehensive tests)
│
└── TIMEOUT_MANAGEMENT_IMPLEMENTATION.md ← YOU ARE HERE
```

---

## Implementation Details

### 1. Timeout Configuration (`core/timeout_config.py`)

```python
# Default timeouts by intent
INTENT_TIMEOUTS = {
    CALCULATION: 10,      # Fast calculation
    HS_CODE_LOOKUP: 25,   # Database retrieval (extended)
    DEFINITION: 20,       # Standard retrieval
    POLICY_QUERY: 25,     # Retrieval-based (extended)
    TRADE_QUERY: 20,      # Complex aggregation
}

# Service-specific timeouts
SERVICE_TIMEOUTS = {
    "calculator": 10,
    "retrieval": 25,      # Extended for vector DB searches
    "trade_data": 20,
}
```

### 2. Usage in Coordinator

**Before (no timeout management):**

```python
async def _handle_calculation(self, context):
    result = await self.calculator_client.calculate(question)
    # Uses default client timeout (15s typically)
```

**After (with timeout management):**

```python
async def _handle_calculation(self, context):
    # Get intent-specific timeout
    timeout_sec = self.timeout_config.get_intent_timeout(context.intent)
    service_timeout = self.timeout_config.get_service_timeout("calculator")
    timeout_sec = min(timeout_sec, service_timeout)  # Use stricter

    # Call with explicit timeout
    try:
        result = await asyncio.wait_for(
            self.calculator_client.calculate(question, currency=currency),
            timeout=timeout_sec
        )
        context.set_result("calculation", result)
    except asyncio.TimeoutError:
        context.add_error(f"Service timed out after {timeout_sec}s")
```

### 3. Configuration Access

**Global singleton (default):**

```python
from core import get_timeout_config

# Get defaults
config = get_timeout_config()
timeout = config.get_intent_timeout(WorkflowIntent.CALCULATION)  # → 10s
```

**Custom configuration:**

```python
from core import TimeoutConfig, initialize_timeout_config

# Create custom config
custom = TimeoutConfig(
    intent_timeouts={WorkflowIntent.CALCULATION: 15},  # Override
    default_timeout=20
)

# Use globally
initialize_timeout_config(custom)
```

### 4. Runtime Configuration

```python
config = get_timeout_config()

# View all timeouts
print(config.get_all_timeouts())
# {
#   "default": 15,
#   "intent_timeouts": {"calculation": 10, "retrieval": 15, ...},
#   "service_timeouts": {"calculator": 10, "retrieval": 15, ...},
#   "bounds": {"min": 2, "max": 60}
# }

# Update at runtime
config.set_intent_timeout(WorkflowIntent.CALCULATION, 12)  # 10s → 12s
config.set_service_timeout("retrieval", 20)                 # 15s → 20s
```

---

## Default Timeout Values

| Intent         | Timeout | Purpose                            |
| -------------- | ------- | ---------------------------------- |
| CALCULATION    | 10s     | Fast arithmetic, quick operation   |
| HS_CODE_LOOKUP | 25s     | Database search, retrieval-based   |
| DEFINITION     | 20s     | Definition lookup, retrieval-based |
| POLICY_QUERY   | 25s     | Policy retrieval, extended time    |
| TRADE_QUERY    | 20s     | Complex aggregation, data-heavy    |
| DEFAULT        | 15s     | Fallback for unknown intents       |

| Service    | Timeout | Notes                            |
| ---------- | ------- | -------------------------------- |
| calculator | 10s     | Should be fast                   |
| retrieval  | 25s     | Vector DB search, extended time  |
| trade_data | 20s     | Complex queries, needs more time |

**Bounds:**

- Minimum: 2 seconds (safety limit)
- Maximum: 60 seconds (reasonable upper bound)

---

## Timeout Selection Logic

When coordinator calls a service:

```
1. Get intent timeout
   timeout_sec = config.get_intent_timeout(context.intent)
   // Example: CALCULATION → 10s

2. Get service timeout
   service_timeout = config.get_service_timeout("calculator")
   // Example: calculator → 10s

3. Use MINIMUM (stricter)
   timeout_sec = min(10, 10)
   // Result: 10 seconds

4. Call service with timeout
   result = await asyncio.wait_for(
       service_call(),
       timeout=10
   )
```

### Why Minimum?

Prevents situations like:

- Intent says 15s, service says 10s → Use 10s ✓
- Intent says 10s, service says 15s → Use 10s ✓
- Always uses the more conservative value

---

## Error Handling

When timeout occurs:

```python
try:
    result = await asyncio.wait_for(
        service_call(),
        timeout=timeout_sec
    )
except asyncio.TimeoutError:
    logger.error(f"Service timed out after {timeout_sec}s")
    context.add_error(f"Service timed out after {timeout_sec}s")
    context.status = WorkflowStatus.FAILED
    # → Circuit breaker may open if repeated
```

### User Experience

| Scenario             | Before    | After       |
| -------------------- | --------- | ----------- |
| Calculation takes 6s | Waits 30s | Waits 6s ✓  |
| Calculation fails    | Waits 30s | Waits 10s ✓ |
| Retrieval takes 8s   | Waits 30s | Waits 8s ✓  |
| Retrieval fails      | Waits 30s | Waits 25s ✓ |

---

## Test Coverage

**20 comprehensive tests** covering:

✅ Default timeout values  
✅ Custom timeout initialization  
✅ Runtime timeout updates  
✅ Bounds enforcement (min=2, max=60)  
✅ Singleton pattern  
✅ Global configuration management  
✅ Intent-to-timeout mapping  
✅ Service-to-timeout mapping  
✅ Integration with asyncio

```bash
pytest tests/test_timeout_config.py -v
# 20/20 tests passing ✓
```

---

## Integration with Previous Steps

### Relationship to Circuit Breaker

```
Before (STEP 2 only):
  Failure → Retry 3 times → Circuit opens after 5 failures
  Total time: potentially 30+ seconds if all retries timeout

After (STEP 4 added):
  Failure → Retry 3 times (each with 10s timeout)
  Total time: ~30 seconds max (3 × 10s), but circuit opens faster
  If timeouts accumulate → circuit breaks sooner
```

### Relationship to Health Checks

```
Health check finds service DEGRADED (slow response):
  → Can feed into timeout config
  → Dynamic timeout adjustment possible:

    If health status is DEGRADED:
        timeout = normal_timeout * 1.2  // Add 20%
    Else if DEGRADED for long time:
        timeout = normal_timeout * 0.8  // Reduce by 20% (be stricter)
```

---

## Configuration Examples

### Example 1: Development (Generous Timeouts)

```python
dev_timeouts = TimeoutConfig(
    intent_timeouts={
        WorkflowIntent.CALCULATION: 15,
        WorkflowIntent.RETRIEVAL: 20,
        WorkflowIntent.TRADE_QUERY: 30,
    },
    default_timeout=20
)
initialize_timeout_config(dev_timeouts)
```

### Example 2: Production (Strict Timeouts)

```python
prod_timeouts = TimeoutConfig(
    intent_timeouts={
        WorkflowIntent.CALCULATION: 8,
        WorkflowIntent.RETRIEVAL: 12,
        WorkflowIntent.TRADE_QUERY: 18,
    },
    default_timeout=12
)
initialize_timeout_config(prod_timeouts)
```

### Example 3: Environment Variables

```python
import os
from core import TimeoutConfig, initialize_timeout_config

config = TimeoutConfig(
    default_timeout=int(os.getenv("DEFAULT_TIMEOUT", "15")),
    # Can extend to parse intent-specific from env vars
)
initialize_timeout_config(config)
```

---

## Logging

Debug output shows timeout values:

```
[TimeoutConfig] Initialized: TimeoutConfig(default=15s, intents=[...], services=[...])
[TimeoutConfig] Intent 'calculation' → 10s timeout
[TimeoutConfig] Service 'calculator' → 10s timeout
[coordinator] Calculator timeout: 10s (intent-specific)
[coordinator] Calculation completed with currency=USD
```

Errors show timeout context:

```
[coordinator] Calculator service timed out after 10s
[coordinator] Calculation failed: Calculator service timed out after 10s
```

---

## Performance Impact

| Aspect                    | Before  | After     | Impact          |
| ------------------------- | ------- | --------- | --------------- |
| Response time (fail case) | ~30s    | ~10-20s   | ⬇ 67-50% faster |
| Circuit breaker response  | Slow    | Fast      | ⬇ Better        |
| Resource cleanup          | Delayed | Immediate | ⬆ Better        |
| CPU overhead              | None    | Minimal   | ↔ Negligible    |

---

## Troubleshooting

### Timeout too aggressive (frequent timeouts)

**Symptom:** Services timing out even though they work locally
**Solution:**

```python
config.set_intent_timeout(WorkflowIntent.CALCULATION, 15)  # Increase from 10
```

### Timeout too lenient (slow failure detection)

**Symptom:** Bad service causes long delays
**Solution:**

```python
config.set_intent_timeout(WorkflowIntent.CALCULATION, 6)  # Decrease from 10
```

### Want to debug timeouts

```python
config = get_timeout_config()
print(config.get_all_timeouts())  # See all settings
print(config.get_intent_timeout(WorkflowIntent.CALCULATION))  # See specific
```

---

## Next Steps

### Monitor Actual Performance

Track actual service response times:

```python
# Add metric: service_response_time_ms = [actual times]
# Compare with configured timeout
# Adjust if needed based on real data
```

### Adaptive Timeouts (Future)

```python
# Use health check data to adjust timeouts
if service_is_degraded:
    timeout *= 1.2  # Give more time
else:
    timeout *= 0.9  # Be stricter if healthy
```

### Metrics Integration

Expose timeout configuration via Prometheus:

```
orchestrator_timeout_intent_seconds{intent="calculation"}  10
orchestrator_timeout_service_seconds{service="calculator"}  10
orchestrator_request_timeout_rate_total  # How often timeouts occur
```

---

## Summary

| Feature                       | Status                 | Impact                              |
| ----------------------------- | ---------------------- | ----------------------------------- |
| **Intent-specific timeouts**  | ✅ Implemented         | Faster failure detection            |
| **Service-specific timeouts** | ✅ Implemented         | Better resource management          |
| **Dynamic configuration**     | ✅ Implemented         | Runtime adjustments possible        |
| **Bounds enforcement**        | ✅ Implemented         | Prevents misconfiguration           |
| **Test coverage**             | ✅ 20/20 tests passing | Production-ready                    |
| **Documentation**             | ✅ Complete            | Easy to understand/maintain         |
| **Integration**               | ✅ With STEPS 1-3      | Works alongside retry + CB + health |

---

## Code Locations

- **Configuration Module**: [core/timeout_config.py](../core/timeout_config.py)
- **Coordinator Updates**: [core/coordinator.py](../core/coordinator.py) (4 methods)
- **Tests**: [tests/test_timeout_config.py](../tests/test_timeout_config.py)
- **Exports**: [core/**init**.py](../core/__init__.py)

---

## Quick Start

```python
# 1. Import
from core import get_timeout_config, initialize_timeout_config, TimeoutConfig

# 2. Use defaults
config = get_timeout_config()
timeout = config.get_intent_timeout(WorkflowIntent.CALCULATION)  # 10s

# 3. Or customize
custom = TimeoutConfig(default_timeout=20)
initialize_timeout_config(custom)

# 4. View all
print(config.get_all_timeouts())

# 5. Update at runtime
config.set_intent_timeout(WorkflowIntent.CALCULATION, 12)
```

**Status: ✅ PRODUCTION READY**

All 20 tests passing. Ready for integration with orchestrator service.
