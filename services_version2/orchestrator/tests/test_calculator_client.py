import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from app.infrastructure.clients import CalculatorServiceClient

@pytest.mark.asyncio
async def test_calculator_client_handles_400_validation_error():
    client = CalculatorServiceClient("http://mock-calculator:8002")
    
    # Construct mock request and response for HTTP 400
    mock_request = httpx.Request("POST", "http://mock-calculator:8002/query")
    mock_response = httpx.Response(
        400,
        json={"detail": "Validation error: Duty rates not found for HS code 0102.39.00"},
        request=mock_request
    )
    mock_error = httpx.HTTPStatusError(
        "Bad Request",
        request=mock_request,
        response=mock_response
    )
    
    # Mock self._post to raise HTTPStatusError
    with patch.object(client, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = mock_error
        
        # Test query method
        result_query = await client.query("Calculate tax for 0102.39.00")
        assert result_query["success"] is False
        assert "Validation error" in result_query["answer"]
        assert "Validation error" in result_query["error"]
        
        # Test calculate method
        result_calc = await client.calculate("Calculate tax for 0102.39.00")
        assert result_calc["success"] is False
        assert "Validation error" in result_calc["answer"]
        assert "Validation error" in result_calc["error"]


@pytest.mark.asyncio
async def test_calculator_client_raises_for_other_errors():
    client = CalculatorServiceClient("http://mock-calculator:8002")
    
    # Construct mock request and response for HTTP 500
    mock_request = httpx.Request("POST", "http://mock-calculator:8002/query")
    mock_response = httpx.Response(500, request=mock_request)
    mock_error = httpx.HTTPStatusError(
        "Internal Server Error",
        request=mock_request,
        response=mock_response
    )
    
    with patch.object(client, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = mock_error
        
        # Ensure 500 raises httpx.HTTPStatusError
        with pytest.raises(httpx.HTTPStatusError):
            await client.query("Calculate tax for 0102.39.00")
            
        with pytest.raises(httpx.HTTPStatusError):
            await client.calculate("Calculate tax for 0102.39.00")
