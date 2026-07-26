import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.infrastructure.clients import GeneralServiceClient

@pytest.mark.asyncio
async def test_general_client_trade_guard_toggles():
    """Verify that GeneralServiceClient._ask correctly toggles require_period_for_trade based on query content."""
    client = GeneralServiceClient("http://localhost:8005")
    
    # Mock the _post method of GeneralServiceClient/HttpxServiceClient
    client._post = AsyncMock(return_value={"status": "success"})
    
    # Case 1: General query with "cost" / "comparison" should set require_period_for_trade to False
    await client.ask(query="import cost comparison CBU vs CKD Honda Civic", session_id="test_sess")
    client._post.assert_called_once()
    payload = client._post.call_args[0][1]
    assert payload["require_period_for_trade"] is False
    
    client._post.reset_mock()
    
    # Case 2: General query with "tax" should set require_period_for_trade to False
    await client.ask(query="how is import tax calculated for motor vehicle", session_id="test_sess")
    payload = client._post.call_args[0][1]
    assert payload["require_period_for_trade"] is False

    client._post.reset_mock()
    
    # Case 3: General query with "procedure" should set require_period_for_trade to False
    await client.ask(query="import procedure for Honda Civic", session_id="test_sess")
    payload = client._post.call_args[0][1]
    assert payload["require_period_for_trade"] is False

    client._post.reset_mock()

    # Case 4: General query without policy/cost/tax terms (e.g. "import comparison") should default to True
    await client.ask(query="import comparison", session_id="test_sess")
    payload = client._post.call_args[0][1]
    assert payload["require_period_for_trade"] is True

    client._post.reset_mock()

    # Case 5: General query with assembly codes (e.g. "CBU") should set require_period_for_trade to False
    await client.ask(query="cbu custom clearance details", session_id="test_sess")
    payload = client._post.call_args[0][1]
    assert payload["require_period_for_trade"] is False
