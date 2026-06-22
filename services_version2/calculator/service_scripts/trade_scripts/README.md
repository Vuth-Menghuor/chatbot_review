# Trade Query v2 Scripts

This folder contains helper scripts to run and test `services_version2/trade_query_version2`.

## Files

- `start_trade_query.ps1`: Starts Trade Query v2 locally on port `8004`.
- `test_trade_query.ps1`: Runs quick endpoint checks against a running Trade Query v2 service.

## Prerequisites

- Windows PowerShell or PowerShell 7+
- Project virtual environment at `env/`
- Dependencies installed (`pip install -r requirements.txt` from repo root)

## Quick Start

1. Start service:

```powershell
cd e:\RAG\GDCE-ChatBot\service_scripts\trade_scripts
.\start_trade_query.ps1
```

2. Run tests (new terminal):

```powershell
cd e:\RAG\GDCE-ChatBot\service_scripts\trade_scripts
.\test_trade_query.ps1
```

## Script Options

### start_trade_query.ps1

```powershell
.\start_trade_query.ps1 -Reload -Debug -Port 8004
```

Parameters:

- `-Reload`: Enable uvicorn auto-reload
- `-Debug`: Use debug log level
- `-Port`: Service port (default `8004`)

### test_trade_query.ps1

```powershell
.\test_trade_query.ps1 -ServiceURL "http://localhost:8004" -MaxWaitTime 30
```

Parameters:

- `-ServiceURL`: Base URL of Trade Query service
- `-MaxWaitTime`: Seconds to wait for health check readiness
- `-TestDelay`: Delay between test groups in ms

## Endpoints Covered by Test Script

- `GET /health`
- `POST /extract-params`
- `POST /query`
- `GET /records?limit=5`

## Notes

- Service is designed to be called by Orchestrator after intent classification (`trade_query`), but direct testing is supported.
- Default runtime port for v2 is `8004`.
