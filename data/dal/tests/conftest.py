"""Shared test configuration and fixtures."""

import os

# Set test environment before any app imports
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

import pytest
from fastapi.testclient import TestClient

from app.main import app


def pytest_collection_modifyitems(items):
  """Treat contract and integration suites as integration tests in CI."""
  for item in items:
    nodeid = item.nodeid.replace("\\", "/")
    if "tests/integration/" in nodeid or "tests/contract/" in nodeid:
      item.add_marker(pytest.mark.integration)


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app, raise_server_exceptions=False)
