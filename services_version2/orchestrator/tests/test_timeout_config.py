"""
Test Suite for Timeout Configuration (STEP 4)
Tests intent-specific timeout management
"""

import pytest
import asyncio
import sys
import os

# Add parent directory to path to find core module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.timeout_config import (
    TimeoutConfig,
    get_timeout_config,
    initialize_timeout_config,
    reset_timeout_config,
)
from core.workflow import WorkflowIntent


class TestTimeoutConfigBasics:
    """Test basic TimeoutConfig functionality."""
    
    def test_default_timeouts(self):
        """Test default timeout values."""
        config = TimeoutConfig()
        
        assert config.get_intent_timeout(WorkflowIntent.CALCULATION) == 10
        assert config.get_intent_timeout(WorkflowIntent.HS_CODE_LOOKUP) == 45
        assert config.get_intent_timeout(WorkflowIntent.GENERAL) == 35
        assert config.get_intent_timeout(WorkflowIntent.TRADE_QUERY) == 20
    
    def test_intent_timeout_with_none(self):
        """Test timeout when intent is None."""
        config = TimeoutConfig(default_timeout=18)
        assert config.get_intent_timeout(None) == 18
    
    def test_service_timeouts(self):
        """Test service-specific timeouts."""
        config = TimeoutConfig()
        
        assert config.get_service_timeout("calculator") == 10
        assert config.get_service_timeout("retrieval") == 45
        assert config.get_service_timeout("trade_data") == 20
    
    def test_service_timeout_unknown(self):
        """Test timeout for unknown service."""
        config = TimeoutConfig()
        assert config.get_service_timeout("unknown_service") == 15  # Default
    
    def test_timeout_bounds(self):
        """Test timeout bounds are enforced."""
        config = TimeoutConfig()
        
        # Minimum bound
        assert config.get_intent_timeout(WorkflowIntent.CALCULATION) >= config.MIN_TIMEOUT
        # Maximum bound
        assert config.get_intent_timeout(WorkflowIntent.TRADE_QUERY) <= config.MAX_TIMEOUT


class TestTimeoutConfigCustomization:
    """Test timeout customization."""
    
    def test_custom_intent_timeouts(self):
        """Test custom intent timeout initialization."""
        custom_timeouts = {
            WorkflowIntent.CALCULATION: 20,
            WorkflowIntent.HS_CODE_LOOKUP: 30,
        }
        config = TimeoutConfig(intent_timeouts=custom_timeouts)
        
        assert config.get_intent_timeout(WorkflowIntent.CALCULATION) == 20
        assert config.get_intent_timeout(WorkflowIntent.HS_CODE_LOOKUP) == 30
    
    def test_custom_service_timeouts(self):
        """Test custom service timeout initialization."""
        custom_service_timeouts = {
            "calculator": 15,
            "retrieval": 25,
        }
        config = TimeoutConfig(service_timeouts=custom_service_timeouts)
        
        assert config.get_service_timeout("calculator") == 15
        assert config.get_service_timeout("retrieval") == 25
    
    def test_set_intent_timeout(self):
        """Test setting intent timeout at runtime."""
        config = TimeoutConfig()
        config.set_intent_timeout(WorkflowIntent.CALCULATION, 25)
        
        assert config.get_intent_timeout(WorkflowIntent.CALCULATION) == 25
    
    def test_set_service_timeout(self):
        """Test setting service timeout at runtime."""
        config = TimeoutConfig()
        config.set_service_timeout("calculator", 18)
        
        assert config.get_service_timeout("calculator") == 18
    
    def test_set_timeout_out_of_bounds(self):
        """Test that out-of-bounds timeouts raise error."""
        config = TimeoutConfig()
        
        # Too small
        with pytest.raises(ValueError):
            config.set_intent_timeout(WorkflowIntent.CALCULATION, 1)
        
        # Too large
        with pytest.raises(ValueError):
            config.set_intent_timeout(WorkflowIntent.CALCULATION, 100)


class TestTimeoutConfigBounds:
    """Test timeout bounds enforcement."""
    
    def test_minimum_timeout_enforcement(self):
        """Test minimum timeout is enforced."""
        config = TimeoutConfig(default_timeout=1)  # Too small
        
        # Should be clamped to MIN_TIMEOUT
        assert config.default_timeout >= config.MIN_TIMEOUT
    
    def test_maximum_timeout_enforcement(self):
        """Test maximum timeout is enforced."""
        config = TimeoutConfig(default_timeout=100)  # Too large
        
        # Should be clamped to MAX_TIMEOUT
        assert config.default_timeout <= config.MAX_TIMEOUT
    
    def test_get_timeout_bounds(self):
        """Test timeout bounds retrieval."""
        config = TimeoutConfig()
        all_timeouts = config.get_all_timeouts()
        
        assert all_timeouts["bounds"]["min"] == config.MIN_TIMEOUT
        assert all_timeouts["bounds"]["max"] == config.MAX_TIMEOUT


class TestTimeoutConfigGlobal:
    """Test global timeout configuration singleton."""
    
    def setup_method(self):
        """Reset global config before each test."""
        reset_timeout_config()
    
    def test_get_global_config(self):
        """Test getting global timeout config."""
        config1 = get_timeout_config()
        config2 = get_timeout_config()
        
        # Should be same instance (singleton)
        assert config1 is config2
    
    def test_initialize_global_config(self):
        """Test initializing global timeout config."""
        reset_timeout_config()
        
        custom_config = TimeoutConfig(default_timeout=25)
        result = initialize_timeout_config(custom_config)
        
        assert result is custom_config
        assert get_timeout_config() is custom_config
        assert get_timeout_config().default_timeout == 25
    
    def test_initialize_with_defaults(self):
        """Test initializing global config with defaults."""
        reset_timeout_config()
        
        result = initialize_timeout_config()
        
        assert result is not None
        assert isinstance(result, TimeoutConfig)


class TestTimeoutConfigIntegration:
    """Integration tests for timeout configuration."""
    
    def test_intent_and_service_timeout_selection(self):
        """Test selecting timeout based on intent and service."""
        config = TimeoutConfig()
        
        # Calculation via calculator: min(10, 10) = 10
        intent_timeout = config.get_intent_timeout(WorkflowIntent.CALCULATION)
        service_timeout = config.get_service_timeout("calculator")
        selected = min(intent_timeout, service_timeout)
        assert selected == 10
        
        # Trade query via trade_data: min(20, 20) = 20
        intent_timeout = config.get_intent_timeout(WorkflowIntent.TRADE_QUERY)
        service_timeout = config.get_service_timeout("trade_data")
        selected = min(intent_timeout, service_timeout)
        assert selected == 20
        
        # HS code lookup via retrieval: min(45, 45) = 45
        intent_timeout = config.get_intent_timeout(WorkflowIntent.HS_CODE_LOOKUP)
        service_timeout = config.get_service_timeout("retrieval")
        selected = min(intent_timeout, service_timeout)
        assert selected == 45
    
    def test_get_all_timeouts_structure(self):
        """Test structure of get_all_timeouts."""
        config = TimeoutConfig()
        all_timeouts = config.get_all_timeouts()
        
        assert "default" in all_timeouts
        assert "intent_timeouts" in all_timeouts
        assert "service_timeouts" in all_timeouts
        assert "bounds" in all_timeouts
        
        assert isinstance(all_timeouts["intent_timeouts"], dict)
        assert isinstance(all_timeouts["service_timeouts"], dict)
        assert isinstance(all_timeouts["bounds"], dict)
        
        # Check that intent names are strings
        for intent_name in all_timeouts["intent_timeouts"].keys():
            assert isinstance(intent_name, str)


class TestTimeoutConfigLogging:
    """Test logging and string representations."""
    
    def test_repr(self):
        """Test string representation."""
        config = TimeoutConfig()
        repr_str = repr(config)
        
        assert "TimeoutConfig" in repr_str
        assert "default=" in repr_str
        assert "intents=" in repr_str
        assert "services=" in repr_str


@pytest.mark.asyncio
class TestTimeoutIntegration:
    """Integration tests with async timeout context."""
    
    async def test_timeout_context_manager(self):
        """Test actual timeout enforcement with asyncio.wait_for."""
        config = TimeoutConfig()
        timeout_sec = config.get_intent_timeout(WorkflowIntent.CALCULATION)
        
        async def quick_operation():
            await asyncio.sleep(0.1)
            return "success"
        
        async def slow_operation():
            await asyncio.sleep(timeout_sec + 5)
            return "failed"
        
        # Quick operation should complete
        try:
            result = await asyncio.wait_for(quick_operation(), timeout=timeout_sec)
            assert result == "success"
        except asyncio.TimeoutError:
            pytest.fail("Quick operation should not timeout")
        
        # Slow operation should timeout
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow_operation(), timeout=timeout_sec)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
