# Retrieval Service Scripts (v2)

This folder contains helper scripts to start and test the Retrieval Service v2.

## Files

- `start_retrieval.ps1`: Starts Retrieval Service v2 on port 8003.
- `test.ps1`: Runs smoke tests against Retrieval v2 endpoints.

## Prerequisites

- PowerShell 5.1+
- Python environment available at `env\Scripts\Activate.ps1` (recommended)
- Qdrant reachable from Retrieval service config

## Start the Service

Run from anywhere:

```powershell
.\service_scripts\retrieval_scripts\start_retrieval.ps1
```

Optional flags:

```powershell
.\service_scripts\retrieval_scripts\start_retrieval.ps1 -Host 127.0.0.1 -Port 8003 -Reload
```

## Run Tests

Make sure the service is already running, then:

```powershell
.\service_scripts\retrieval_scripts\test.ps1
```

Optional flags:

```powershell
.\service_scripts\retrieval_scripts\test.ps1 -BaseUrl http://127.0.0.1:8003 -TimeoutSec 20
```

## Expected Base Path

Retrieval v2 endpoints use:

- Base path: `/v1`
- Health: `GET /v1/health`
- General retrieval: `POST /v1/retrieval/retrieve`
- Intent endpoints:
  - `POST /v1/hs-code-lookup`
  - `POST /v1/definition`
  - `POST /v1/policy-inquiry`
  - `POST /v1/general`
