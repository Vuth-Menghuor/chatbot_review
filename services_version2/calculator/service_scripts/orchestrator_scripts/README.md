# GDCE Orchestrator Service v2

**Overview**: Central query router and coordinator for the GDCE ChatBot system. Routes natural language questions to appropriate backend services (Calculator, Retrieval, Trade Data) with intelligent intent detection and response formatting.

**Version**: 2.0.0  
**Status**: Production Ready ✅  
**Port**: 8001 (default)

---

## 📋 Quick Start

### 1. Start the Service

```powershell
# Using the provided script
.\start_orchestrator_v2.ps1

# Or manually start the service
cd ..\..\services_version2\orchestrator_version2
python main.py
```

**Expected Output:**

```
============================================================
GDCE Orchestrator Service v2
============================================================
Starting service on 127.0.0.1:8001
🟢 Orchestrator v2.0 Ready
   Listening on 127.0.0.1:8001
   API Docs: http://127.0.0.1:8001/docs
============================================================
```

### 2. Test the Service

```powershell
# Using the provided test script
.\test_orchestrator.ps1

# Or manually test an endpoint
curl -X POST http://localhost:8001/query `
  -H "Content-Type: application/json" `
  -d '{
    "question": "Calculate tax for HS 0102.29.11 CIF $800 from China",
    "session_id": "session_test_001"
  }'
```

### 3. Access API Documentation

Open in browser: **http://localhost:8001/docs**

---

## 🎯 Service Capabilities

### Supported Intents (6 Types)

| Intent             | Service           | Example Query                              |
| ------------------ | ----------------- | ------------------------------------------ |
| **calculation**    | Calculator (8002) | "Calculate tax for HS 0102.29.11 CIF $800" |
| **hs_code_lookup** | Retrieval (8003)  | "What is the HS code for chickens?"        |
| **definition**     | Retrieval (8003)  | "Define CIF in customs terminology"        |
| **policy_query**   | Retrieval (8003)  | "What are FTA requirements?"               |
| **trade_query**    | Trade Data (8004) | "Trade data: export to Thailand"           |
| **general**        | Retrieval (8003)  | "Tell me about customs procedures"         |

### Processing Features

- ✅ **Two-Layer Intent Detection**: LLM-based (primary) + keyword-based (fallback)
- ✅ **Three-Stage Input Validation**: Security → Scope → Format
- ✅ **Service Routing**: Routes to appropriate backend (Calculator, Retrieval, Trade Data)
- ✅ **Output Validation**: Ensures accuracy and safety
- ✅ **LLM Response Formatting**: Enhanced readability with step-by-step explanations
- ✅ **Citations & Metadata**: Tracks data sources and processing details

---

## 📡 API Endpoints

### 1. POST /query — Process Query

Process a user question with full validation and service routing.

**Request:**

```json
{
  "question": "Calculate tax for HS 0102.29.11 CIF $800 from China",
  "session_id": "session_abc123"
}
```

**Response:**

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "question": "Calculate tax for HS 0102.29.11 CIF $800 from China",
  "answer": "For HS code 0102.29.11... [formatted response]",
  "intent": "calculation",
  "status": "completed",
  "latency_ms": 245.5,
  "citations": [
    {
      "source": "PostgreSQL",
      "url": "172.25.3.243:5432",
      "accessed": "2026-04-02T10:30:00Z"
    }
  ],
  "metadata": {
    "llm_intent_detection": true,
    "confidence": 0.96,
    "layer": "layer_1_llm"
  }
}
```

### 2. POST /chat — Chat Endpoint

Alias for /query. Same functionality with a familiar endpoint name.

### 3. GET /health — Health Check

Check health of orchestrator and all dependent services.

**Response:**

```json
{
  "status": "healthy",
  "version": "2.0.0",
  "timestamp": "2026-04-02T10:30:00Z",
  "services": {
    "calculator": {
      "status": "healthy",
      "latency_ms": 5.2
    },
    "retrieval": {
      "status": "healthy",
      "latency_ms": 12.1
    },
    "trade_data": {
      "status": "healthy",
      "latency_ms": 8.5
    }
  }
}
```

### 4. GET /status — Service Status

Get detailed orchestrator service status including configuration.

### 5. GET /info — Service Information

Get service capabilities and available endpoints.

### 6. POST /query/explain — Debug Intent Detection

Show how a query would be routed (for debugging).

**Request:**

```json
{
  "question": "What is the HS code for tomatoes?"
}
```

**Response:**

```json
{
  "intent": "hs_code_lookup",
  "intent_confidence": "high",
  "intended_workflow": {
    "primary_service": "retrieval",
    "validation_required": true,
    "output_formatting": true
  }
}
```

---

## 🔍 Example Queries by Intent

### Calculation

```
"Calculate import tax for HS 0102.29.11, CIF $800 from China"
"How much duty on $500 FOB value from Thailand?"
"What's the total tax including VAT for $1000 import from Vietnam?"
```

### HS Code Lookup

```
"What is the HS code for chickens?"
"Find HS code for Honda motorcycles"
"Classify: electronic components"
```

### Definition

```
"Define CIF in customs"
"What does FOB mean?"
"Explain: tariff rate"
```

### Policy Query

```
"What are RCEP FTA requirements?"
"Cambodia-Thailand trade agreement details"
"What documents do I need for ASEAN trade?"
```

### Trade Query

```
"Trade data: import value from China 2024"
"Export statistics to Thailand"
"Bilateral trade Cambodia-Vietnam"
```

### General

```
"Tell me about customs procedures"
"How do Cambodia customs work?"
"General import/export information"
```

---

## ⚙️ Configuration

### Environment Variables (.env)

**Service Ports:**

```
ORCHESTRATOR_HOST=127.0.0.1
ORCHESTRATOR_PORT=8001
CALCULATOR_PORT=8002
RETRIEVAL_PORT=8003
TRADE_DATA_PORT=8004
```

**Database & Services:**

```
PG_HOST=172.25.3.243
PG_PORT=5432
PG_DATABASE=gdce_hs_code
QDRANT_HOST=172.25.3.243
QDRANT_PORT=6333
```

**LLM Intent Detection:**

```
LLM_INTENT_DETECTION=true              # Enable LLM-based intent detection
LLM_TIMEOUT_MS=2000                    # Timeout for LLM classification
LLM_FALLBACK_TO_LAYER_2_ON_TIMEOUT=true
```

**Response Formatting:**

```
LLM_RESPONSE_FORMATTING_ENABLED=true   # Enable LLM response formatting
LLM_RESPONSE_FORMAT=structured_json    # Format type
```

**Validation & Security:**

```
INPUT_VALIDATION_ENABLED=true          # Validate user input
OUTPUT_VALIDATION_ENABLED=true         # Validate service output
SECURITY_CHECK_ENABLED=true            # Check for injection attacks
```

### Configuration Files

Located in `configs/orchestrator/`:

| File                          | Purpose                                    |
| ----------------------------- | ------------------------------------------ |
| `intent_detection_rules.json` | Layer 1 LLM config + Layer 2 keyword rules |
| `service_routing.json`        | Workflow sequences for all 6 intents       |
| `validation_rules.json`       | Injection patterns + scope keywords        |
| `response_formatting.json`    | Response format templates                  |

---

## 🔧 Troubleshooting

### Service Won't Start

**Error**: Port 8001 already in use

```powershell
# Find and kill process on port 8001
Get-NetTCPConnection -LocalPort 8001 | Stop-Process -Force
# Then restart the service
```

**Error**: Python not found

```powershell
# Activate virtual environment first
& .\env\Scripts\Activate.ps1
# Then start the service
python main.py
```

### Service Starts but No Responses

**Check**: Are backend services running?

```powershell
# Test individual services
curl http://localhost:8002/health  # Calculator
curl http://localhost:8003/health  # Retrieval
curl http://localhost:8004/health  # Trade Data
```

**Check**: API health endpoint

```powershell
.\test_orchestrator.ps1  # Run full test suite
```

### Queries Returning Errors

**Check**: Input validation

```powershell
# Use /query/explain to debug intent detection
curl -X POST http://localhost:8001/query/explain `
  -H "Content-Type: application/json" `
  -d '{"question": "Your question here"}'
```

**Check**: Service logs

```powershell
# Service logs are printed to console during startup
# Look for [ERROR] or [WARNING] messages
```

### Slow Responses

**Check**: Service timeouts

- Calculation queries timeout after 30 seconds
- Retrieval queries timeout after 15 seconds
- Trade data queries timeout after 20 seconds

**Optimize**:

- Make sure database connections are healthy
- Check LLM timeout setting (default 2 seconds)

---

## 📊 Service Architecture

```
┌─────────────────────────────────────────┐
│  User Interface / Chat Frontend         │
└────────────────┬────────────────────────┘
                 │ HTTP POST /query
                 ▼
┌─────────────────────────────────────────┐
│  Orchestrator Service (Port 8001)       │
│  ├─ Input Validation                    │
│  ├─ Intent Detection (2-Layer)          │
│  ├─ Service Routing                     │
│  ├─ Response Formatting                 │
│  └─ Output Validation                   │
└─────┬─────────┬─────────┬───────────────┘
      │         │         │
      ▼         ▼         ▼
 Calculator  Retrieval  Trade Data
 (8002)      (8003)     (8004)
      │         │         │
      └─────┬───┴───┬─────┘
            ▼       ▼
      PostgreSQL + Qdrant
```

---

## 📝 Scripts

### start_orchestrator_v2.ps1

Starts the orchestrator service with proper error handling and logging.

```powershell
.\start_orchestrator_v2.ps1
```

### test_orchestrator.ps1

Runs comprehensive tests on the orchestrator service.

```powershell
.\test_orchestrator.ps1

# What it tests:
# 1. Service availability (/health)
# 2. Service info (/info)
# 3. Intent detection (/query/explain)
# 4. Calculation query (/query)
# 5. HS code lookup (/query)
# 6. Health of backend services
```

---

## 📚 Additional Resources

- **Full Architecture**: See [ORCHESTRATOR_V2_ARCHITECTURE.md](../../services_version2/orchestrator_version2/ORCHESTRATOR_V2_ARCHITECTURE.md)
- **Implementation Details**: See [IMPLEMENTATION_APPLIED.md](../../services_version2/orchestrator_version2/IMPLEMENTATION_APPLIED.md)
- **API Documentation**: http://localhost:8001/docs (Swagger UI)
- **ReDoc Documentation**: http://localhost:8001/redoc (Alternative API docs)

---

## 🆘 Support

**For issues or questions:**

1. Check the [Troubleshooting](#-troubleshooting) section above
2. Review service logs in console output
3. Use `/query/explain` endpoint for intent detection debugging
4. Check `/health` endpoint for backend service status
5. See ORCHESTRATOR_V2_ARCHITECTURE.md for complete technical details

---

**Last Updated**: April 2, 2026  
**Version**: 2.0.0  
**Status**: Production Ready ✅
