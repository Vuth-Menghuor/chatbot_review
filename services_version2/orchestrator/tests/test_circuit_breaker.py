#!/usr/bin/env python3
"""
Circuit Breaker Integration Test
Tests the actual CircuitBreaker pattern at the application level
Shows fast-fail behavior when circuit opens
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from services_version2.orchestrator.infrastructure.clients import (
    HttpxServiceClient,
    CircuitBreakerConfig,
    RetryConfig
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CircuitBreakerTester:
    """Test the circuit breaker pattern with various failure scenarios."""
    
    def __init__(self):
        """Initialize the tester with test configurations."""
        # Create client pointing to non-existent service (will fail)
        retry_config = RetryConfig(
            max_retries=2,
            initial_backoff_ms=100,
            exponential_base=2.0
        )
        
        cb_config = CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout_sec=60,
            name="TestCircuitBreaker"
        )
        
        # Point to port that doesn't exist to trigger failures
        self.client = HttpxServiceClient(
            base_url="http://127.0.0.1:9999",
            timeout=1,
            retry_config=retry_config,
            circuit_breaker_config=cb_config
        )
    
    async def run_test_sequence(self, num_requests: int = 15):
        """
        Run a sequence of requests to trigger circuit breaker behavior.
        
        Expected sequence:
        - Requests 1-5: Fail with retries (~700ms each with 2 retries)
        - Request 6: Circuit opens, fast-fail (<50ms)
        - Requests 7-15: Fast-fail (<50ms each)
        """
        print("\n" + "="*70)
        print("CIRCUIT BREAKER INTEGRATION TEST")
        print("="*70)
        print("\nTesting with non-existent service on port 9999")
        print(f"Sending {num_requests} requests...\n")
        
        results = []
        
        for request_num in range(1, num_requests + 1):
            start_time = time.time()
            duration_ms = 0
            status = "PENDING"
            
            try:
                # Try to make a request to non-existent service
                result = await self.client._post("test", {"data": "test"})
                status = "SUCCESS"
            
            except Exception as e:
                status = f"FAILED ({type(e).__name__})"
            
            finally:
                duration_ms = (time.time() - start_time) * 1000
                cb_state = self.client.circuit_breaker.state.value.upper()
                
                results.append({
                    "request": request_num,
                    "duration_ms": duration_ms,
                    "status": status,
                    "cb_state": cb_state
                })
                
                # Print result
                if duration_ms < 100:
                    marker = "[FAST-FAIL]"
                else:
                    marker = "[RETRY]    "
                
                print(f"Request {request_num:2d} : {duration_ms:7.1f}ms {marker} {cb_state:10s} - {status}")
        
        # Summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        
        fast_fails = sum(1 for r in results if r['duration_ms'] < 100)
        retries = sum(1 for r in results if r['duration_ms'] >= 100)
        
        print(f"\nFast-fails (<100ms): {fast_fails}")
        print(f"Retries (>= 100ms): {retries}")
        
        # Expected vs Actual
        print("\nEXPECTED BEHAVIOR:")
        print("  Requests 1-5:   Fail with retries (~700ms each)")
        print("  Request 6:      Circuit OPENS - fast-fail detected")
        print("  Requests 7-15:  Fast-fail (<50ms each) - circuit is OPEN")
        
        print("\nACTUAL BEHAVIOR:")
        if retries <= 5 and fast_fails >= 9:
            print("  ✓ PASS - Circuit breaker working correctly!")
            print(f"  - First {retries} requests used retries")
            print(f"  - Remaining {fast_fails} requests fast-failed")
        else:
            print(f"  ✗ FAIL - Unexpected behavior")
            print(f"  - Expected: 5 retries + 10 fast-fails")
            print(f"  - Got: {retries} retries + {fast_fails} fast-fails")
        
        # Circuit breaker final state
        cb_info = self.client.circuit_breaker.get_state_info()
        print(f"\nCircuit Breaker Final State:")
        print(f"  State: {cb_info['state'].upper()}")
        print(f"  Failure Count: {cb_info['failure_count']}")
        print(f"  Success Count: {cb_info['success_count']}")
        print(f"  Uptime: {cb_info['uptime_seconds']:.2f}s")
        
        print("\n" + "="*70)
        
        await self.client.close()


async def main():
    """Main entry point."""
    tester = CircuitBreakerTester()
    await tester.run_test_sequence(num_requests=15)


if __name__ == "__main__":
    asyncio.run(main())
