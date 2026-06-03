"""
Test Suite: Retry Logic with Exponential Backoff
Tests the HttpxServiceClient retry mechanisms for handling transient failures
"""

import sys
import os
from pathlib import Path

# Add parent directory to path so we can import infrastructure
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
import httpx
from datetime import datetime, timedelta

from infrastructure.clients import (
    HttpxServiceClient,
    RetryConfig,
    RetrievalServiceClient,
    CalculatorServiceClient,
)


class TestRetryConfig:
    """Test RetryConfig calculation logic."""
    
    def test_default_config(self):
        """Test default retry configuration."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.initial_backoff_ms == 100
        assert config.max_backoff_ms == 10000
        assert config.exponential_base == 2.0
    
    def test_exponential_backoff_calculation(self):
        """Test exponential backoff increases appropriately."""
        config = RetryConfig(initial_backoff_ms=100, exponential_base=2.0, jitter=False)
        
        # Attempt 0: 100ms
        assert config.get_backoff_ms(0) == 100
        
        # Attempt 1: 200ms (100 * 2^1)
        assert config.get_backoff_ms(1) == 200
        
        # Attempt 2: 400ms (100 * 2^2)
        assert config.get_backoff_ms(2) == 400
        
        # Attempt 3: 800ms (100 * 2^3)
        assert config.get_backoff_ms(3) == 800
    
    def test_backoff_capped_at_max(self):
        """Test backoff is capped at maximum value."""
        config = RetryConfig(
            initial_backoff_ms=1000,
            max_backoff_ms=5000,
            exponential_base=2.0,
            jitter=False
        )
        
        # Without cap: 1000 * 2^5 = 32000
        # With cap: 5000
        assert config.get_backoff_ms(5) == 5000
    
    def test_jitter_adds_randomness(self):
        """Test jitter adds variance to backoff."""
        config = RetryConfig(initial_backoff_ms=1000, jitter=True)
        
        backoffs = [config.get_backoff_ms(0) for _ in range(10)]
        
        # All should be close to 1000ms but not exactly (due to jitter)
        for backoff in backoffs:
            assert 900 <= backoff <= 1100  # 1000 +/- 10%


@pytest.mark.asyncio
class TestHttpxServiceClientRetryLogic:
    """Test HttpxServiceClient retry behavior."""
    
    async def test_get_success_on_first_attempt(self):
        """Test successful request on first attempt (no retries needed)."""
        client = HttpxServiceClient("http://localhost:8000")
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok", "data": "test"}
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            result = await client._get("health")
            
            assert result == {"status": "ok", "data": "test"}
            mock_get.assert_called_once()
    
    async def test_post_success_on_first_attempt(self):
        """Test successful POST request on first attempt."""
        client = HttpxServiceClient("http://localhost:8000")
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": "success"}
        
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            result = await client._post("calculate", {"value": 100})
            
            assert result == {"result": "success"}
            mock_post.assert_called_once()
    
    async def test_retry_on_connection_error(self):
        """Test retry logic handles connection errors."""
        config = RetryConfig(max_retries=2, initial_backoff_ms=10, jitter=False)
        client = HttpxServiceClient("http://localhost:8000", retry_config=config)
        
        # Fail first 2 times, succeed on 3rd attempt
        side_effects = [
            httpx.ConnectError("Connection failed"),
            httpx.ConnectError("Connection failed"),
            MagicMock(json=MagicMock(return_value={"status": "ok"}))
        ]
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = side_effects
            
            result = await client._get("health")
            
            # Should have retried and succeeded on 3rd call
            assert result == {"status": "ok"}
            assert mock_get.call_count == 3
    
    async def test_retry_on_timeout_error(self):
        """Test retry logic handles timeout errors."""
        config = RetryConfig(max_retries=2, initial_backoff_ms=10, jitter=False)
        client = HttpxServiceClient("http://localhost:8000", retry_config=config)
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "recovered"}
        
        side_effects = [
            httpx.TimeoutException("Request timed out"),
            httpx.TimeoutException("Request timed out"),
            mock_response
        ]
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = side_effects
            
            result = await client._get("health")
            
            assert result == {"status": "recovered"}
            assert mock_get.call_count == 3
    
    async def test_retry_on_500_error(self):
        """Test retry logic handles 5xx HTTP errors."""
        config = RetryConfig(max_retries=2, initial_backoff_ms=10, jitter=False)
        client = HttpxServiceClient("http://localhost:8000", retry_config=config)
        
        # Create mock responses
        mock_error_response = MagicMock()
        mock_error_response.status_code = 500
        
        mock_ok_response = MagicMock()
        mock_ok_response.json.return_value = {"status": "ok"}
        
        side_effects = [
            httpx.HTTPStatusError("500 error", request=MagicMock(), response=mock_error_response),
            httpx.HTTPStatusError("503 error", request=MagicMock(), response=MagicMock(status_code=503)),
            mock_ok_response
        ]
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = side_effects
            
            result = await client._get("health")
            
            assert result == {"status": "ok"}
            assert mock_get.call_count == 3
    
    async def test_no_retry_on_400_error(self):
        """Test that 4xx HTTP errors are NOT retried (except 429)."""
        config = RetryConfig(max_retries=3)
        client = HttpxServiceClient("http://localhost:8000", retry_config=config)
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "404 not found",
                request=MagicMock(),
                response=mock_response
            )
            
            with pytest.raises(httpx.HTTPStatusError):
                await client._get("invalid_endpoint")
            
            # Should only try once (no retries)
            assert mock_get.call_count == 1
    
    async def test_retry_on_429_rate_limit(self):
        """Test that 429 (rate limit) errors ARE retried."""
        config = RetryConfig(max_retries=2, initial_backoff_ms=10, jitter=False)
        client = HttpxServiceClient("http://localhost:8000", retry_config=config)
        
        mock_error_response = MagicMock()
        mock_error_response.status_code = 429
        
        mock_ok_response = MagicMock()
        mock_ok_response.json.return_value = {"status": "ok"}
        
        side_effects = [
            httpx.HTTPStatusError("429 rate limited", request=MagicMock(), response=mock_error_response),
            httpx.HTTPStatusError("429 rate limited", request=MagicMock(), response=mock_error_response),
            mock_ok_response
        ]
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = side_effects
            
            result = await client._get("health")
            
            assert result == {"status": "ok"}
            assert mock_get.call_count == 3
    
    async def test_exhaust_retries_and_fail(self):
        """Test that exception is raised after retries exhausted."""
        config = RetryConfig(max_retries=2, initial_backoff_ms=10, jitter=False)
        client = HttpxServiceClient("http://localhost:8000", retry_config=config)
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("Always fails")
            
            with pytest.raises(httpx.ConnectError):
                await client._get("health")
            
            # Should have tried max_retries + 1 times
            assert mock_get.call_count == 3  # Initial + 2 retries
    
    async def test_backoff_delay_increases(self):
        """Test that backoff delays increase with each retry."""
        config = RetryConfig(max_retries=2, initial_backoff_ms=50, exponential_base=2.0, jitter=False)
        client = HttpxServiceClient("http://localhost:8000", retry_config=config)
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get, \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep, \
             patch('infrastructure.clients.logger') as mock_logger:
            
            mock_get.side_effect = [
                httpx.ConnectError("Fail 1"),
                httpx.ConnectError("Fail 2"),
                mock_response
            ]
            
            result = await client._get("health")
            
            # Check sleep was called with increasing delays
            assert mock_sleep.call_count == 2
            # First sleep: 50ms, Second sleep: 100ms
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert sleep_calls[0] == 0.05  # 50ms
            assert sleep_calls[1] == 0.10  # 100ms
    
    async def test_post_with_retry(self):
        """Test POST request with retry and recovery."""
        config = RetryConfig(max_retries=1, initial_backoff_ms=10, jitter=False)
        client = HttpxServiceClient("http://localhost:8000", retry_config=config)
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"calculation": "done"}
        
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [
                httpx.TimeoutException("First attempt timed out"),
                mock_response
            ]
            
            result = await client._post("calculate", {"hs_code": "0102.29.11"})
            
            assert result == {"calculation": "done"}
            assert mock_post.call_count == 2


@pytest.mark.asyncio
class TestRetrievalServiceClientRetry:
    """Test RetrievalServiceClient with retry logic."""
    
    async def test_retrieve_with_retry(self):
        """Test retrieve operation with transient failure and recovery."""
        config = RetryConfig(max_retries=1, initial_backoff_ms=10, jitter=False)
        client = RetrievalServiceClient("http://localhost:8001", retry_config=config)
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "documents": [{"text": "doc1"}],
            "query": "test"
        }
        
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [
                httpx.TimeoutException("First attempt timed out"),
                mock_response
            ]
            
            result = await client.retrieve("test question", collection="gdce_docs")
            
            assert len(result["documents"]) == 1
            assert mock_post.call_count == 2


@pytest.mark.asyncio
class TestCalculatorServiceClientRetry:
    """Test CalculatorServiceClient with retry logic."""
    
    async def test_calculate_with_retry(self):
        """Test calculate operation with transient failure and recovery."""
        config = RetryConfig(max_retries=2, initial_backoff_ms=10, jitter=False)
        client = CalculatorServiceClient("http://localhost:8002/v1", retry_config=config)
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "total_tax": 150.00,
            "currency": "USD"
        }
        
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            # Fail twice, succeed on third attempt
            mock_post.side_effect = [
                httpx.ConnectError("Connection refused"),
                httpx.TimeoutException("Timeout"),
                mock_response
            ]
            
            result = await client.calculate("How much duty for HS 0102.29.11 worth $100?")
            
            assert result["total_tax"] == 150.00
            assert mock_post.call_count == 3

    def test_parse_question_extracts_cif_phrase(self):
        parsed = CalculatorServiceClient._parse_question_for_calculation(
            "calculate import tax hs 0102.29.19 cif 4000 from china"
        )

        assert parsed["hs_code"] == "0102.29.19"
        assert parsed["cif_value"] == 4000.0
        assert parsed["origin_country"] == "China"

    def test_parse_question_explicit_currency_over_country(self):
        parsed = CalculatorServiceClient._parse_question_for_calculation(
            "8000 dollars from China"
        )

        assert parsed["currency"] == "USD"
        assert parsed["currency_provided"] is True
        assert parsed["origin_country"] == "China"

    def test_parse_question_yen_symbol_maps_to_cny(self):
        parsed = CalculatorServiceClient._parse_question_for_calculation(
            "¥8000 from USA"
        )

        assert parsed["currency"] == "CNY"
        assert parsed["currency_provided"] is True
        assert parsed["origin_country"] == "Usa"

    def test_parse_question_broken_yen_symbol_is_sanitized(self):
        parsed = CalculatorServiceClient._parse_question_for_calculation(
            "Â¥8000 from USA"
        )

        assert parsed["currency"] == "CNY"
        assert parsed["currency_provided"] is True

    def test_parse_question_defaults_to_khr_when_no_currency_and_no_country(self):
        parsed = CalculatorServiceClient._parse_question_for_calculation(
            "calculate import tax for electronics with cif 8000"
        )

        assert parsed["currency"] == "KHR"
        assert parsed["currency_provided"] is False
        assert parsed["origin_country"] is None

    def test_parse_question_compact_currency_format(self):
        parsed = CalculatorServiceClient._parse_question_for_calculation(
            "CIF 8000usd from China"
        )

        assert parsed["cif_value"] == 8000.0
        assert parsed["currency"] == "USD"
        assert parsed["currency_provided"] is True

    def test_parse_question_currency_prefix_format(self):
        parsed = CalculatorServiceClient._parse_question_for_calculation(
            "CIF USD 8000 from China"
        )

        assert parsed["cif_value"] == 8000.0
        assert parsed["currency"] == "USD"
        assert parsed["currency_provided"] is True

    def test_parse_question_yen_word_format(self):
        parsed = CalculatorServiceClient._parse_question_for_calculation(
            "Import tax for HS 0102.29.11, 100000 yen from Japan"
        )

        assert parsed["hs_code"] == "0102.29.11"
        assert parsed["cif_value"] == 100000.0
        assert parsed["currency"] == "JPY"
        assert parsed["currency_provided"] is True
        assert parsed["origin_country"] == "Japan"

    def test_parse_question_symbol_suffix_format(self):
        parsed = CalculatorServiceClient._parse_question_for_calculation(
            "CIF 8000$ from China"
        )

        assert parsed["cif_value"] == 8000.0
        assert parsed["currency"] == "USD"
        assert parsed["currency_provided"] is True

    def test_parse_question_import_country_phrase(self):
        parsed = CalculatorServiceClient._parse_question_for_calculation(
            "CIF 8000 import from China"
        )

        assert parsed["origin_country"] == "China"

    def test_parse_question_export_country_phrase(self):
        parsed = CalculatorServiceClient._parse_question_for_calculation(
            "CIF 8000 export to Cambodia"
        )

        assert parsed["origin_country"] == "Cambodia"

    def test_parse_question_dq_factor_and_dv(self):
        parsed = CalculatorServiceClient._parse_question_for_calculation(
            "calculate import tax for hs code 8703.80.99 cif 40000USD DV = 0.00 DQ = 40% ACFTA from china"
        )
        assert parsed["dq_factor"] == 0.40
        assert parsed["dq_applicable"] is True
        assert parsed["declared_value"] == 0.00

@pytest.mark.asyncio
class TestRealWorldScenarios:
    """Test real-world failure scenarios."""
    
    async def test_service_temporary_unavailable_then_recovers(self):
        """Simulate service that is temporarily down but recovers."""
        config = RetryConfig(max_retries=3, initial_backoff_ms=20, jitter=False)
        client = HttpxServiceClient("http://localhost:8000", retry_config=config)
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "healthy"}
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            # Service down for first 2 attempts, recovers on 3rd
            mock_get.side_effect = [
                httpx.ConnectError("Service unreachable"),
                httpx.ConnectError("Service unreachable"),
                mock_response
            ]
            
            start = datetime.now()
            result = await client._get("health")
            duration = (datetime.now() - start).total_seconds()
            
            assert result == {"status": "healthy"}
            # Should have delays: 20ms + 40ms = 60ms minimum
            assert duration >= 0.06
    
    async def test_cascading_failures_eventually_fail(self):
        """Test that cascading failures eventually fail after retries exhausted."""
        config = RetryConfig(max_retries=2)
        client = HttpxServiceClient("http://localhost:8000", retry_config=config)
        
        with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Always times out")
            
            with pytest.raises(httpx.TimeoutException):
                await client._get("health")
            
            # Should attempt 3 times (initial + 2 retries)
            assert mock_get.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
