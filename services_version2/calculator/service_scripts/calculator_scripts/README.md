# Running Scripts for GDCE Calculator Service v2

This folder contains PowerShell scripts for starting and testing the Calculator Service v2.

## Quick Start

### 1. Start the Service

```powershell
.\start_calculator_v2.ps1
```

**Output:**

```
Starting Calculator Service (port 8002)...
Endpoint: http://127.0.0.1:8002
API Docs: http://127.0.0.1:8002/docs
```

### 2. Test the Service

In a new PowerShell terminal:

```powershell
.\test_calculator_v2.ps1
```

**Expected Output:**

```
✅ Service Status: healthy
✅ Test PASSED
Total Payment: 321,800 KHR
```

---

## Script Documentation

### `start_calculator_v2.ps1`

**Purpose:** Launch the Calculator Service v2 microservice

**Usage:**

```powershell
# Basic startup
.\start_calculator_v2.ps1

# With debug logging
.\start_calculator_v2.ps1 -Debug

# With auto-reload (development)
.\start_calculator_v2.ps1 -Reload

# On custom port
.\start_calculator_v2.ps1 -Port 9000
```

**Parameters:**

- `-Reload` : Enable auto-reload on code changes (development mode)
- `-Debug` : Enable debug logging
- `-Port <number>` : Custom port (default: 8002)

**What it does:**

1. ✅ Validates service directory exists
2. ✅ Sets up Python environment
3. ✅ Verifies .env configuration
4. ✅ Starts FastAPI server on port 8002
5. ✅ Shows data source configuration (Qdrant, PostgreSQL, CSV)

**Data Sources:**

- **Primary:** Qdrant (172.25.3.243:6333) for duty rates
- **Secondary:** PostgreSQL (172.25.3.243:5432) for exchange rates
- **Fallback:** CSV files in `data/raw/tables/`

---

### `test_calculator_v2.ps1`

**Purpose:** Test the Calculator Service v2 with sample requests

**Usage:**

```powershell
# Basic test
.\test_calculator_v2.ps1

# Verbose output (shows full JSON)
.\test_calculator_v2.ps1 -Verbose

# Against remote service
.\test_calculator_v2.ps1 -ServiceUrl "http://your-server:8002"
```

**Parameters:**

- `-ServiceUrl <url>` : Service endpoint (default: http://127.0.0.1:8002)
- `-Verbose` : Show full JSON responses

**What it tests:**

1. ✅ Health check - Verify service and database connectivity
2. ✅ Calculate import tax - Normal case (live cattle example)
3. ✅ Validates KHR-first calculation flow
4. ✅ Shows exchange rate applied
5. ✅ Displays tax breakdown

**Sample Request:**

```json
{
  "calculation_date": "2026-04-01",
  "regime": "import",
  "goods": {
    "hs_code": "0102.29.11",
    "description": "Live cattle"
  },
  "valuation": {
    "customs_value": 800,
    "currency": "USD"
  }
}
```

**Expected Response:**

```
Total Payment: 321,800 KHR
Exchange Rate: 1 USD = 4022 KHR
Tax Breakdown:
  • Customs Duty: 0 KHR
  • Special Tax: 0 KHR
  • VAT: 321,760 KHR
```

---

## Complete Workflow

### Terminal 1: Start Services

```powershell
# Activate virtual environment (if needed)
.\env\Scripts\Activate.ps1

# Navigate to running scripts
cd running_scripts

# Start calculator service
.\start_calculator_v2.ps1
```

**Keep this terminal open - service will display logs here**

### Terminal 2: Test Service

```powershell
cd running_scripts

# Run tests
.\test_calculator_v2.ps1

# Or test with verbose output
.\test_calculator_v2.ps1 -Verbose
```

### Terminal 3: Use API

```powershell
# Manual API test with curl
curl -X POST http://localhost:8002/calculate_import_taxes `
  -H "Content-Type: application/json" `
  -d '{
    "calculation_date": "2026-04-01",
    "regime": "import",
    "goods": {"hs_code": "0102.29.11", "description": "Live cattle"},
    "valuation": {"customs_value": 800, "currency": "USD"}
  }'
```

---

## Troubleshooting

### "Service not responding"

- ✅ Verify service is running in Terminal 1
- ✅ Check port 8002 is not in use: `netstat -ano | findstr :8002`
- ✅ Verify Qdrant is accessible: `curl http://172.25.3.243:6333/health`

### "Cannot find Qdrant/PostgreSQL"

- ✅ Check network connectivity: `ping 172.25.3.243`
- ✅ Service will use CSV fallback if remote sources unavailable
- ✅ Check logs in service terminal for data source status

### "Python module not found"

- ✅ Verify virtual environment: `.\env\Scripts\Activate.ps1`
- ✅ Install dependencies: `pip install -r requirements.txt`
- ✅ Check PYTHONPATH is set correctly in start script

### Permission Denied

- ✅ Run PowerShell as Administrator
- ✅ Or set execution policy: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

---

## API Endpoints

| Method | Endpoint                     | Purpose                                |
| ------ | ---------------------------- | -------------------------------------- |
| GET    | `/`                          | Service info                           |
| GET    | `/health`                    | Health check with database status      |
| POST   | `/calculate_import_taxes` | Calculate import taxes (main endpoint) |
| GET    | `/docs`                      | API documentation (Swagger UI)         |
| GET    | `/lookup/duty-rate`          | Look up duty rates by HS code          |
| GET    | `/lookup/hs-info`            | Get HS code description                |
| GET    | `/lookup/exchange-rate`      | Get exchange rate for currency         |

---

## Configuration

### Environment Variables (`.env`)

Located at: `services_version2/calculator_version2/.env`

**Key settings:**

```bash
# Qdrant configuration
QDRANT_HOST=172.25.3.243
QDRANT_PORT=6333
QDRANT_COLLECTION=gdce_hs_code

# PostgreSQL configuration
PG_HOST=172.25.3.243
PG_PORT=5432
PG_DATABASE=gdce_hs_code

# Fallback exchange rate
USD_TO_KHR_RATE_FALLBACK=4022.0
```

---

## Performance Tips

1. **Development Mode:** Use `-Reload` for auto-reload

   ```powershell
   .\start_calculator_v2.ps1 -Reload
   ```

2. **Batch Testing:** Create a test script

   ```powershell
   for ($i = 1; $i -le 10; $i++) {
       .\test_calculator_v2.ps1
   }
   ```

3. **Monitor Logs:** Keep service terminal visible for real-time logs

4. **Health Monitoring:** Periodic health checks
   ```powershell
   while ($true) {
       curl http://localhost:8002/health
       Start-Sleep -Seconds 30
   }
   ```

---

## Support

For issues or questions:

1. Check logs in service terminal
2. Visit API docs: http://127.0.0.1:8002/docs
3. Review Calculator Architecture: `services_version2/CALCULATOR_V2_ARCHITECTURE.md`
4. Check configuration: `services_version2/calculator_version2/.env`
