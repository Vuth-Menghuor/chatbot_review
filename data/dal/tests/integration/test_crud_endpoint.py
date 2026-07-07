"""Integration tests for metadata CRUD routes."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


TABLE_PATHS = [
    "dataset",
    "dataset-version",
    "dataset-mapping",
    "api-key",
    "api-key-dataset",
    "cache-policy",
    "audit-log",
]


@pytest.mark.parametrize("table_path", TABLE_PATHS)
def test_list_requires_api_key(client, table_path):
    resp = client.get(f"/v1/crud/{table_path}")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "MISSING_API_KEY"


@pytest.mark.parametrize("table_path", TABLE_PATHS)
def test_create_requires_api_key(client, table_path):
    resp = client.post(f"/v1/crud/{table_path}", json={})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "MISSING_API_KEY"


@pytest.mark.parametrize("table_path", TABLE_PATHS)
def test_item_routes_require_api_key(client, table_path):
    item_id = str(uuid4())

    get_resp = client.get(f"/v1/crud/{table_path}/{item_id}")
    patch_resp = client.patch(f"/v1/crud/{table_path}/{item_id}", json={})
    delete_resp = client.delete(f"/v1/crud/{table_path}/{item_id}")

    assert get_resp.status_code == 401
    assert patch_resp.status_code == 401
    assert delete_resp.status_code == 401
    assert get_resp.json()["error"]["code"] == "MISSING_API_KEY"
    assert patch_resp.json()["error"]["code"] == "MISSING_API_KEY"
    assert delete_resp.json()["error"]["code"] == "MISSING_API_KEY"
