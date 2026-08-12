"""
conftest.py
 
Shared config/fixtures for direct, per-service unit testing — bypasses the
orchestrator entirely and hits each microservice's own endpoint. This is
separate from test_rag_regression.py, which tests the full orchestrator
pipeline end-to-end.
 
Use this file's SERVICE_CONFIG to point at each service directly:
  - via docker network (if running tests from inside the compose network):
        calculator:8002, retrieval-service:8003, trade-service:8004, general-service:8005
  - via localhost (if running tests from the host machine, using mapped ports):
        set the *_URL env vars below to your actual mapped ports.
 
--------------------------------------------------------------------------
SCHEMA CONFIDENCE — adjust as needed
--------------------------------------------------------------------------
CONFIRMED from logs/traces in this project:
  - calculator:        POST /query   body: {"question": "<string>"}
  - retrieval-service:  POST /hs-code-candidates   body: {"query": "<string>", "mode": "best", "top_k": 5}
 
ASSUMED (not yet confirmed) — adjust path/body/method below once verified:
  - trade-service:      POST /query   body: {"question": "<string>"}
  - general-service:     POST /query   body: {"question": "<string>"}
"""
 
 
import os 
import pytest 


SERVICE_CONFIG = {
    "calculator" : {
        "base_url": os.environ.get("CALCULATOR_SERVICE_URL",  "http://localhost:8002"),
        "path": "/query",
        "build_body": lambda query, extra: {"question": query, **(extra or {})}
    },

    "retrieval" : {
        "base_url": os.environ.get("RETRIEVAL_SERVICE_URL",  "http://localhost:8003"),
        "path": "/hs-code-candidates",
        "build_body": lambda query, extra: {
            "query": query, 
            "mode": (extra or {}).get("mode", "best"),
            "top_k": (extra or {}).get("top_k", 5)
        }
    },
    "general-service" : {
        "base_url": os.environ.get("GENERAL_SERVICE_URL",  "http://localhost:8005"),
        "path": "/retrieval/retrieve",
        "build_body": lambda query, extra: {
            "query": query, 
            "mode": (extra or {}).get("mode", "best"),
            "top_k": (extra or {}).get("top_k", 5)
        }
    },
    "trade" : {
        "base_url": os.environ.get("TRADE_SERVICE_URL",  "http://localhost:8004"),
        "path": "/query",
        "build_body": lambda query, extra: {"question": query, **(extra or {})}
    },
}

HEALTH_PATH = "/heath"
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "30.0"))

@pytest.fixture(scope="session")
def service_config():
    return SERVICE_CONFIG