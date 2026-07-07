"""
Infrastructure Clients - Service adapters
Handles communication with dependent services
Includes retry logic with exponential backoff
"""

import logging
import asyncio
from typing import Optional, Dict, Any, Callable, TypeVar
import aiohttp
import httpx
from enum import Enum
import time
from dataclasses import dataclass
from datetime import datetime

try:
    from core.logging import get_request_id
except Exception:
    from ..core.logging import get_request_id

logger = logging.getLogger(__name__)

# Type variable for generic retry function
T = TypeVar('T')


class RetryConfig:
    """Configuration for retry logic."""
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_backoff_ms: int = 100,
        max_backoff_ms: int = 10000,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        """
        Initialize retry configuration.
        
        Args:
            max_retries: Maximum number of retry attempts (default: 3)
            initial_backoff_ms: Initial backoff in milliseconds (default: 100)
            max_backoff_ms: Maximum backoff in milliseconds (default: 10000)
            exponential_base: Exponential multiplier for backoff (default: 2.0)
            jitter: Whether to add random jitter to backoff (default: True)
        """
        self.max_retries = max_retries
        self.initial_backoff_ms = initial_backoff_ms
        self.max_backoff_ms = max_backoff_ms
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def get_backoff_ms(self, attempt: int) -> int:
        """Calculate backoff time in milliseconds for given attempt."""
        import random
        
        # Calculate exponential backoff: initial_backoff * (base ^ attempt)
        backoff = self.initial_backoff_ms * (self.exponential_base ** attempt)
        backoff = min(backoff, self.max_backoff_ms)  # Cap at max
        
        # Add jitter to avoid thundering herd
        if self.jitter:
            jitter_amount = random.uniform(0, backoff * 0.1)  # 10% jitter
            backoff += jitter_amount
        
        return int(backoff)


class RetryableException(Exception):
    """Marks an exception as retryable (transient failure)."""
    pass


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"          # Normal operation, allowing requests
    OPEN = "open"              # Failing fast, blocking requests
    HALF_OPEN = "half_open"    # Testing recovery, allowing limited requests


class CircuitBreakerConfig:
    """Configuration for circuit breaker pattern."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_sec: int = 60,
        half_open_max_calls: int = 2,
        name: str = "CircuitBreaker"
    ):
        """
        Initialize circuit breaker configuration.
        
        Args:
            failure_threshold: Number of failures to open circuit (default: 5)
            recovery_timeout_sec: Seconds to wait before attempting recovery (default: 60)
            half_open_max_calls: Number of calls allowed in HALF_OPEN state (default: 2)
            name: Name for logging purposes (default: "CircuitBreaker")
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self.half_open_max_calls = half_open_max_calls
        self.name = name


class CircuitBreaker:
    """
    Circuit Breaker pattern implementation.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail fast
    - HALF_OPEN: Testing recovery, limited requests allowed
    """
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        """
        Initialize circuit breaker.
        
        Args:
            config: CircuitBreakerConfig object
        """
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change_time: float = time.time()
    
    def is_closed(self) -> bool:
        """Check if circuit is closed (accepting requests)."""
        return self.state == CircuitBreakerState.CLOSED
    
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)."""
        return self.state == CircuitBreakerState.OPEN
    
    def is_half_open(self) -> bool:
        """Check if circuit is in half-open state (testing recovery)."""
        return self.state == CircuitBreakerState.HALF_OPEN
    
    def get_state_info(self) -> Dict[str, Any]:
        """Get detailed circuit breaker state information."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "last_state_change_time": self.last_state_change_time,
            "uptime_seconds": time.time() - self.last_state_change_time,
        }
    
    async def call(
        self,
        operation_name: str,
        operation_func: Callable[[], Any]
    ) -> Any:
        """
        Execute operation through circuit breaker.
        
        Args:
            operation_name: Name of operation for logging
            operation_func: Async function to execute
            
        Returns:
            Result from operation_func
            
        Raises:
            Exception: Either from operation or circuit breaker (if open)
        """
        # Check if we need to attempt recovery
        if self.state == CircuitBreakerState.OPEN:
            time_since_failure = time.time() - self.last_failure_time
            if time_since_failure >= self.config.recovery_timeout_sec:
                logger.info(
                    f"[{self.config.name}] Recovery timeout reached ({time_since_failure:.1f}s). "
                    f"Transitioning OPEN → HALF_OPEN"
                )
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                self.last_state_change_time = time.time()
            else:
                # Circuit still open, fail fast
                logger.warning(
                    f"[{self.config.name}] Circuit is OPEN. Failing fast. "
                    f"Recovery in {self.config.recovery_timeout_sec - time_since_failure:.1f}s"
                )
                raise Exception(
                    f"Circuit breaker is OPEN for {self.config.name}. "
                    f"Service unavailable. Recovery in {self.config.recovery_timeout_sec - time_since_failure:.1f}s"
                )
        
        # In HALF_OPEN state, limit the number of calls
        if self.state == CircuitBreakerState.HALF_OPEN:
            if self.success_count >= self.config.half_open_max_calls:
                logger.warning(
                    f"[{self.config.name}] HALF_OPEN call limit reached ({self.success_count}/{self.config.half_open_max_calls}). "
                    f"Waiting for success to close circuit"
                )
                raise Exception(
                    f"Circuit breaker {self.config.name} is in HALF_OPEN state with max calls reached"
                )
        
        # Execute the operation
        try:
            logger.debug(f"[{self.config.name}] Executing operation: {operation_name} (state: {self.state.value})")
            result = await operation_func()
            
            # Success - handle state transitions
            self._on_success()
            logger.debug(f"[{self.config.name}] Operation succeeded: {operation_name}")
            return result
        
        except Exception as e:
            # Failure - track and potentially open circuit
            self._on_failure(operation_name, e)
            raise
    
    def _on_success(self):
        """Handle successful operation."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            logger.info(
                f"[{self.config.name}] HALF_OPEN success ({self.success_count}/{self.config.half_open_max_calls})"
            )
            
            # If enough successes, close the circuit
            if self.success_count >= self.config.half_open_max_calls:
                logger.info(f"[{self.config.name}] Recovery successful! Transitioning HALF_OPEN → CLOSED")
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.last_state_change_time = time.time()
        
        elif self.state == CircuitBreakerState.CLOSED:
            # Reset failure count on successful operation
            if self.failure_count > 0:
                logger.debug(f"[{self.config.name}] Resetting failure count on successful operation")
                self.failure_count = 0
    
    def _on_failure(self, operation_name: str, error: Exception):
        """Handle failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        logger.warning(
            f"[{self.config.name}] Operation failed: {operation_name}. "
            f"Failures: {self.failure_count}/{self.config.failure_threshold}. "
            f"Error: {type(error).__name__}"
        )
        
        if self.state == CircuitBreakerState.CLOSED:
            # Check if we should open the circuit
            if self.failure_count >= self.config.failure_threshold:
                logger.error(
                    f"[{self.config.name}] Failure threshold reached ({self.failure_count}). "
                    f"Transitioning CLOSED → OPEN"
                )
                self.state = CircuitBreakerState.OPEN
                self.last_state_change_time = time.time()
        
        elif self.state == CircuitBreakerState.HALF_OPEN:
            # Any failure in half-open state reopens the circuit
            logger.error(
                f"[{self.config.name}] Failure in HALF_OPEN state. "
                f"Transitioning HALF_OPEN → OPEN"
            )
            self.state = CircuitBreakerState.OPEN
            self.failure_count = self.config.failure_threshold  # Ensure it stays open
            self.last_state_change_time = time.time()
    
    def manual_open(self):
        """Manually open the circuit (for maintenance)."""
        logger.warning(f"[{self.config.name}] Manual override: Opening circuit")
        self.state = CircuitBreakerState.OPEN
        self.last_failure_time = time.time()
        self.last_state_change_time = time.time()
    
    def manual_close(self):
        """Manually close the circuit (for recovery)."""
        logger.info(f"[{self.config.name}] Manual override: Closing circuit")
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_state_change_time = time.time()


class BaseServiceClient:
    """Base client for service communication."""
    
    def __init__(self, base_url: str, timeout: Optional[int] = 15):
        """
        Initialize service client.
        
        Args:
            base_url: Base URL of the service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.timeout = timeout
    
    async def _get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make GET request."""
        raise NotImplementedError
    
    async def _post(self, endpoint: str, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Make POST request."""
        raise NotImplementedError


class HttpxServiceClient(BaseServiceClient):
    """Service client using httpx library with built-in retry logic and circuit breaker."""
    
    def __init__(
        self,
        base_url: str,
        timeout: Optional[int] = 15,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None
    ):
        """
        Initialize httpx-based service client with retry configuration and circuit breaker.
        
        Args:
            base_url: Base URL of the service
            timeout: Request timeout in seconds (default: 15)
            retry_config: RetryConfig object (default: standard config with 3 retries)
            circuit_breaker_config: CircuitBreakerConfig object (default: standard config)
        """
        super().__init__(base_url, timeout)
        self.client = httpx.AsyncClient(timeout=timeout)
        self.retry_config = retry_config or RetryConfig()
        
        # Initialize circuit breaker with service name
        cb_config = circuit_breaker_config or CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout_sec=60,
            name=f"CircuitBreaker[{base_url.split('/')[-1]}]"
        )
        self.circuit_breaker = CircuitBreaker(cb_config)
    
    async def _execute_with_retry(
        self,
        operation_name: str,
        operation_func: Callable[[], Any]
    ) -> Any:
        """
        Execute an operation with retry logic wrapped in circuit breaker.
        
        Circuit Breaker Flow:
        1. CLOSED: Normal operation, execute with retries
        2. OPEN: Fail fast without retrying
        3. HALF_OPEN: Test recovery with limited requests
        
        Args:
            operation_name: Name of operation for logging
            operation_func: Async function to execute
            
        Returns:
            Result from operation_func
            
        Raises:
            Exception: If circuit is open or all retries exhausted
        """
        async def execute_with_circuit_breaker():
            """Execute operation through circuit breaker."""
            last_exception = None
            
            for attempt in range(self.retry_config.max_retries + 1):
                try:
                    logger.debug(f"[{operation_name}] Attempt {attempt + 1}/{self.retry_config.max_retries + 1}")
                    result = await operation_func()
                    
                    if attempt > 0:
                        logger.info(f"[{operation_name}] Success after {attempt} retries")
                    
                    return result
                
                except (httpx.ConnectError, httpx.TimeoutException, asyncio.TimeoutError) as e:
                    # Transient errors - retry these
                    last_exception = e
                    
                    if attempt >= self.retry_config.max_retries:
                        logger.error(f"[{operation_name}] All {self.retry_config.max_retries + 1} attempts failed. Last error: {e}")
                        raise
                    
                    backoff_ms = self.retry_config.get_backoff_ms(attempt)
                    backoff_sec = backoff_ms / 1000.0
                    logger.warning(
                        f"[{operation_name}] Attempt {attempt + 1} failed with transient error: {type(e).__name__}. "
                        f"Retrying in {backoff_sec:.2f}s... ({attempt + 1}/{self.retry_config.max_retries})"
                    )
                    await asyncio.sleep(backoff_sec)
                
                except httpx.HTTPStatusError as e:
                    # HTTP status errors - check if retryable (5xx, 429)
                    status_code = e.response.status_code
                    
                    if status_code >= 500 or status_code == 429:  # 5xx or rate limit
                        last_exception = e
                        
                        if attempt >= self.retry_config.max_retries:
                            logger.error(f"[{operation_name}] All attempts failed. HTTP {status_code}")
                            raise
                        
                        backoff_ms = self.retry_config.get_backoff_ms(attempt)
                        backoff_sec = backoff_ms / 1000.0
                        logger.warning(
                            f"[{operation_name}] HTTP {status_code} (retryable). Retrying in {backoff_sec:.2f}s..."
                        )
                        await asyncio.sleep(backoff_sec)
                    else:
                        # 4xx errors (except 429) are not retryable
                        logger.error(f"[{operation_name}] HTTP {status_code} (not retryable): {e}")
                        raise
                
                except httpx.RequestError as e:
                    # Other request errors - check if retryable
                    if isinstance(e, (httpx.ConnectError, httpx.TimeoutException)):
                        last_exception = e
                        if attempt >= self.retry_config.max_retries:
                            logger.error(f"[{operation_name}] All attempts failed: {e}")
                            raise
                        
                        backoff_ms = self.retry_config.get_backoff_ms(attempt)
                        backoff_sec = backoff_ms / 1000.0
                        logger.warning(
                            f"[{operation_name}] Request error (retryable): {type(e).__name__}. "
                            f"Retrying in {backoff_sec:.2f}s..."
                        )
                        await asyncio.sleep(backoff_sec)
                    else:
                        logger.error(f"[{operation_name}] Non-retryable request error: {e}")
                        raise
                
                except Exception as e:
                    # Unexpected errors - don't retry
                    logger.error(f"[{operation_name}] Unexpected error (not retrying): {e}")
                    raise
            
            # Should not reach here, but just in case
            if last_exception:
                raise last_exception
        
        # Execute the retry logic through the circuit breaker
        return await self.circuit_breaker.call(operation_name, execute_with_circuit_breaker)
    
    async def _get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make GET request with retry logic and correlation ID propagation.
        
        Args:
            endpoint: Endpoint path
            **kwargs: Additional arguments to pass to httpx
            
        Returns:
            JSON response
        """
        url = f"{self.base_url}/{endpoint}"
        
        async def get_operation():
            # Propagate correlation ID to downstream services
            headers = kwargs.get('headers', {})
            request_id = get_request_id()
            if request_id:
                headers['X-Request-ID'] = request_id
                kwargs['headers'] = headers
            
            response = await self.client.get(url, **kwargs)
            response.raise_for_status()
            return response.json()
        
        return await self._execute_with_retry(f"GET {endpoint}", get_operation)
    
    async def _post(self, endpoint: str, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Make POST request with retry logic, circuit breaker protection, and correlation ID propagation.
        
        Args:
            endpoint: Endpoint path
            data: Request payload
            **kwargs: Additional arguments to pass to httpx
            
        Returns:
            JSON response
        """
        url = f"{self.base_url}/{endpoint}"
        
        async def post_operation():
            # Propagate correlation ID to downstream services
            headers = kwargs.get('headers', {})
            request_id = get_request_id()
            if request_id:
                headers['X-Request-ID'] = request_id
                kwargs['headers'] = headers
            
            response = await self.client.post(url, json=data, **kwargs)
            response.raise_for_status()
            return response.json()
        
        return await self._execute_with_retry(f"POST {endpoint}", post_operation)
    
    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return self.circuit_breaker.get_state_info()
    
    async def close(self):
        """Close the async client."""
        await self.client.aclose()


class RetrievalServiceClient(HttpxServiceClient):
    """
    Client for HS retrieval service (port 8003).
    Endpoints: POST /hs-code-candidates, POST /hs-code-ranked
    """
    
    async def hs_code_lookup(
        self,
        query: str,
        top_k: int = 5,
        generate_answer: bool = True,
        hs_mode: str = "best",
        selected_code: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        HS code classification/discovery endpoint.
        
        Args:
            query: The search query (e.g., "muzzle-loading firearms")
            top_k: Candidate pool size (recommended default: 5)
            generate_answer: Whether to produce final_answer (recommended: true for select mode)
            hs_mode: "best" (default) | "select" | "compare"
            selected_code: Required for hs_mode="select" — the chosen HS code to validate
            session_id: Optional session identifier
            
        Returns:
            HS validation result with candidates, validation status, and optional final_answer
        """
        logger.info(f"[HS Lookup] Querying: {query[:80]}... (mode={hs_mode}, top_k={top_k})")
        
        try:
            payload = {
                "query": query,
                "top_k": top_k,
                "generate_answer": generate_answer,
                "collection": "gdce_hs_code",
                "hs_mode": hs_mode,
                "intent": "hs_code_lookup"  # Sync with orchestrator's WorkflowIntent.HS_CODE_LOOKUP
            }
            
            if selected_code:
                payload["selected_code"] = selected_code
            if session_id:
                payload["session_id"] = session_id
            
            result = await self._post("hs-code-candidates", payload)
            
            # Log key result fields for debugging
            status = result.get("status", "unknown")
            hs_valid = result.get("hs_validation", {})
            primary = hs_valid.get("primary_code", "N/A")
            logger.info(
                f"[HS Lookup] Result: status={status}, primary_code={primary}, "
                f"candidates={len(hs_valid.get('candidates', []))} docs={len(result.get('documents', []))}"
            )
            
            return result
        except Exception as e:
            logger.error(f"[HS Lookup] Error: {e}")
            raise
    
    async def health(self) -> Dict[str, Any]:
        """Check health of HS retrieval service."""
        try:
            return await self._get("health")
        except Exception as e:
            logger.error(f"Retrieval service health check failed: {e}")
            raise


class GeneralServiceClient(HttpxServiceClient):
    """
    Client for general ask/generate service (port 8005).
    Endpoint: POST /ask
    """

    async def _ask(
        self,
        query: str,
        top_k: int = 5,
        generate_answer: bool = True,
        session_id: Optional[str] = None,
        intent: str = "general",
    ) -> Dict[str, Any]:
        payload = {
            "query": query,
            "top_k": top_k,
            "generate_answer": generate_answer,
            "intent": intent,
        }
        if session_id:
            payload["session_id"] = session_id
        return await self._post("retrieval/retrieve", payload)


    async def ask(
        self,
        query: str,
        top_k: int = 5,
        generate_answer: bool = True,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        logger.info(f"[Ask] Querying: {query[:80]}... (top_k={top_k})")
        try:
            result = await self._ask(query, top_k, generate_answer, session_id, intent="general")
            logger.info(
                f"[Ask] Result: status={result.get('status', 'unknown')}, "
                f"final_answer_present={'final_answer' in result}"
            )
            return result
        except Exception as e:
            logger.error(f"[Ask] Error: {e}")
            raise

    async def definition(
        self,
        query: str,
        top_k: int = 5,
        generate_answer: bool = True,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        logger.info(f"[Definition] Querying: {query[:80]}... (top_k={top_k})")
        return await self._ask(query, top_k, generate_answer, session_id, intent="definition")

    async def policy_inquiry(
        self,
        query: str,
        top_k: int = 5,
        generate_answer: bool = True,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        logger.info(f"[Policy] Querying: {query[:80]}... (top_k={top_k})")
        return await self._ask(query, top_k, generate_answer, session_id, intent="policy_query")

    async def general(
        self,
        query: str,
        top_k: int = 5,
        generate_answer: bool = True,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.ask(query, top_k, generate_answer, session_id)

    async def health(self) -> Dict[str, Any]:
        try:
            return await self._get("health")
        except Exception as e:
            logger.error(f"General service health check failed: {e}")
            raise


class CalculatorServiceClient(HttpxServiceClient):
    """Client for calculator service."""

    @staticmethod
    def _sanitize_currency_text(text: str) -> str:
        """Normalize common mojibake currency symbols before parsing."""
        if not text:
            return text

        normalized = text
        replacements = {
            "Â¥": "¥",
            "â¹": "₹",
            "ï¿¥": "¥",
            "＄": "$",
        }
        for broken, clean in replacements.items():
            normalized = normalized.replace(broken, clean)

        return normalized

    @staticmethod
    def _extract_explicit_currency(question: str) -> Optional[str]:
        """
        Extract user-provided currency from symbols, ISO codes, or common names.
        User-provided currency always has highest priority.
        """
        import re

        q = CalculatorServiceClient._sanitize_currency_text(question)
        token_pattern = (
            r"USD|CNY|KHR|EUR|GBP|THB|VND|JPY|KRW|INR|"
            r"dollars?|bucks?|greenbacks?|quid|pounds?|yuan|rmb|renminbi|riels?|yen|"
            r"[$¥៛€£฿₫₩₹]"
        )

        for match in re.finditer(token_pattern, q, re.IGNORECASE):
            normalized = CalculatorServiceClient._normalize_currency_token(match.group(0))
            if normalized:
                return normalized

        return None

    @staticmethod
    def _normalize_currency_token(token: str) -> Optional[str]:
        """Normalize a currency token/symbol to ISO currency code."""
        if not token:
            return None

        cleaned = CalculatorServiceClient._sanitize_currency_text(token).strip().lower()
        alias_map = {
            "usd": "USD", "dollar": "USD", "dollars": "USD", "buck": "USD", "bucks": "USD", "greenback": "USD", "greenbacks": "USD", "$": "USD",
            "cny": "CNY", "yuan": "CNY", "rmb": "CNY", "renminbi": "CNY", "¥": "CNY",
            "khr": "KHR", "riel": "KHR", "riels": "KHR", "៛": "KHR",
            "eur": "EUR", "euro": "EUR", "euros": "EUR", "€": "EUR",
            "gbp": "GBP", "pound": "GBP", "pounds": "GBP", "quid": "GBP", "£": "GBP",
            "thb": "THB", "baht": "THB", "฿": "THB",
            "vnd": "VND", "dong": "VND", "₫": "VND",
            "jpy": "JPY", "yen": "JPY",
            "krw": "KRW", "won": "KRW", "₩": "KRW",
            "inr": "INR", "rupee": "INR", "rupees": "INR", "₹": "INR",
        }
        return alias_map.get(cleaned)

    @staticmethod
    def _extract_amount_and_currency(question: str) -> Dict[str, Any]:
        """Extract customs value + currency from flexible user formats."""
        import re

        q = CalculatorServiceClient._sanitize_currency_text(question)
        number_pattern = r"(?P<amt>\d+(?:,\d{3})*(?:\.\d{1,2})?)"
        token_pattern = (
            r"(?P<cur>USD|CNY|KHR|EUR|GBP|THB|VND|JPY|KRW|INR|"
            r"dollars?|bucks?|greenbacks?|quid|pounds?|yuan|rmb|renminbi|riels?|yen|[$¥៛€£฿₫₩₹])"
        )

        patterns = [
            rf"{token_pattern}\s*{number_pattern}",  # USD 8000, $8000, ¥8000
            rf"{number_pattern}\s*{token_pattern}",  # 8000USD, 8000 usd, 8000$
        ]

        for pattern in patterns:
            match = re.search(pattern, q, re.IGNORECASE)
            if not match:
                continue

            amount_raw = (match.group("amt") or "").replace(",", "")
            currency_raw = match.group("cur")
            currency = CalculatorServiceClient._normalize_currency_token(currency_raw)

            if not currency:
                continue

            try:
                amount = float(amount_raw)
            except ValueError:
                continue

            return {
                "cif_value": amount,
                "currency": currency,
                "currency_provided": True,
            }

        return {
            "cif_value": None,
            "currency": None,
            "currency_provided": False,
        }
    
    @staticmethod
    def _parse_question_for_calculation(question: str) -> Dict[str, Any]:
        """
        Parse natural language question to extract calculation parameters.
        
        Handles patterns like:
        - "Calculate import duty for HS 0102.29.11 CIF $800 from China"
        - "What tax for live oxen worth $5000 from Thailand?"
        - "Duty rate for HS code 0702.00.00"
        
        Args:
            question: Natural language question
            
        Returns:
            Dictionary with extracted parameters
        """
        import re
        
        sanitized_question = CalculatorServiceClient._sanitize_currency_text(question)

        params = {
            "description": sanitized_question,  # Use full question as description for HS lookup
            "hs_code": None,
            "cif_value": None,
            "currency": None,
            "currency_provided": False,
            "origin_country": None,
            "quantity": None,
            "unit": None,
            "regime": "import"
        }

        q_lower = sanitized_question.lower()

        explicit_currency = CalculatorServiceClient._extract_explicit_currency(sanitized_question)
        if explicit_currency:
            params["currency"] = explicit_currency
            params["currency_provided"] = True
        
        # Extract HS code (format: XXXX.XX.XX or XXXX or HS followed by digits)
        hs_patterns = [
            r'hs\s+code\s+(\d{4}(?:\.\d{2}){0,2}|\d{6}|\d{8})',      # hs code 0102.29.11 or 010229 or 01022911
            r'hs\s+(\d{4}(?:\.\d{2}){0,2}|\d{6}|\d{8})',             # hs 0102.29.11 or 010229 or 01022911
            r'(\d{8})',                                                 # 8-digit raw code (01022911)
            r'(\d{4}\.\d{2}\.\d{2})',                                   # dotted 4.2.2 format
            r'(\d{4}\.\d{2})',                                          # dotted 4.2 format
            r'(\d{6})',                                                 # 6-digit raw code (010229)
            r'(?:code\s+)?(\d{4}(?:\s+\d{2}){1,2})',                  # legacy: code 0102 29 11 (no bare 4-digit amounts)
        ]
        for pattern in hs_patterns:
            match = re.search(pattern, q_lower)
            if match:
                hs_code = match.group(1).strip()
                # Normalize to X.XX format if raw digits
                if hs_code.isdigit():
                    if len(hs_code) == 8:
                        hs_code = f"{hs_code[:4]}.{hs_code[4:6]}.{hs_code[6:8]}"
                    elif len(hs_code) == 6:
                        hs_code = f"{hs_code[:4]}.{hs_code[4:6]}"
                    # 4-digit codes stay as-is
                else:
                    # Handle space-separated format (code 0102 29 11)
                    hs_code = hs_code.replace(' ', '.')
                params["hs_code"] = hs_code
                break
        
        # Extract amount+currency in flexible formats first.
        amount_currency = CalculatorServiceClient._extract_amount_and_currency(sanitized_question)
        if amount_currency["cif_value"] is not None:
            params["cif_value"] = amount_currency["cif_value"]
        if amount_currency["currency"] and not params["currency_provided"]:
            params["currency"] = amount_currency["currency"]
            params["currency_provided"] = amount_currency["currency_provided"]

        # Fallback amount extraction when currency token is not present (e.g., "CIF 8000").
        if params["cif_value"] is None:
            cif_only_match = re.search(r'cif\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?)', sanitized_question, re.IGNORECASE)
            if cif_only_match:
                try:
                    params["cif_value"] = float(cif_only_match.group(1).replace(',', ''))
                except ValueError:
                    pass

        # Extract origin country
        # Supports multi-word countries: "from New Zealand", "from South Korea", etc.
        country_patterns = [
            r'\bfrom\s+([a-z][a-z\s\-]{1,60}?)(?=\s+(?:cif|fob|hs|code|with|using|under|for|at|on|in|goods|product|cattle|oxen|\d)|$)',
            r'\bof\s+([a-z][a-z\s\-]{1,60}?)(?=\s+(?:cif|fob|hs|code|with|using|under|for|at|on|in|goods|product|cattle|oxen|\d)|$)',
            r'\borigin\s+([a-z][a-z\s\-]{1,60}?)(?=\s+(?:cif|fob|hs|code|with|using|under|for|at|on|in|goods|product|cattle|oxen|\d)|$)',
            r'\bimport(?:ed)?\s+(?:from\s+)?([a-z][a-z\s\-]{1,60}?)(?=\s+(?:cif|fob|hs|code|with|using|under|for|at|on|in|goods|product|cattle|oxen|\d)|$)',
            r'\bexport(?:ed)?\s+(?:to\s+|from\s+)?([a-z][a-z\s\-]{1,60}?)(?=\s+(?:cif|fob|hs|code|with|using|under|for|at|on|in|goods|product|cattle|oxen|\d)|$)',
            r'\s+([a-z][a-z\s\-]{1,60}?)\s+(?:cattle|oxen|goods|product)',
        ]
        for pattern in country_patterns:
            match = re.search(pattern, q_lower)
            if match:
                country_raw = match.group(1).strip(" ,.-")
                country_clean = re.sub(r'\s+', ' ', country_raw)
                country = country_clean.title()
                # Filter out common non-country words
                if country.lower() not in ['the', 'a', 'an', 'is', 'are', 'for', 'to', 'on', 'tax', 'duty', 'import', 'export']:
                    params["origin_country"] = country
                    break

        # Final fallback default: keep KHR when currency and country are not provided.
        if not params["currency"] and not params["origin_country"]:
            params["currency"] = "KHR"
        
        # Detect explicit FTA mentions (e.g., ACFTA, ATIGA) and set flags
        # Also map natural language certificate mentions like 'form e' → ACFTA
        cert_map = {
            "form d": "ATIGA",
            "form e": "ACFTA",
            "form ak": "AKFTA",
            "form aj": "AJCEP",
            "form rcep": "RCEP",
            "form aanz": "AANZFTA",
            "form aan": "AANZFTA",
            "acfta": "ACFTA",
            "atiga": "ATIGA",
            "rcep": "RCEP",
            "akfta": "AKFTA",
            "ajcep": "AJCEP",
        }

        # First look for explicit certificate phrases (short forms like 'form e')
        for pattern, cert_type in cert_map.items():
            if re.search(rf"\b{re.escape(pattern)}\b", q_lower):
                params["fta_applicable"] = True
                params["fta_certificate_type"] = cert_type
                break

        # Fallback: recognises direct FTA name mentions
        if not params.get("fta_certificate_type"):
            fta_match = re.search(r"\b(acfta|atiga|fta|rcep|cptpp|akfta|ajcep)\b", q_lower, re.IGNORECASE)
            if fta_match:
                fta_code = fta_match.group(1).upper()
                params["fta_applicable"] = True
                params["fta_certificate_type"] = fta_code

        # Certificate → origin inference (reverse mapping)
        cert_origin_map = {
            "ATIGA": "VN",
            "ACFTA": "CN",
            "AKFTA": "KR",
            "AJCEP": "JP",
            "RCEP": "CN",
            "AANZFTA": "AU",
            "AIFTA": "IN",
        }
        cert = params.get("fta_certificate_type")
        if cert and cert in cert_origin_map:
            if not params.get("origin_country"):
                params["origin_country"] = cert_origin_map[cert]

        # Common FTAs like ACFTA/ATIGA often imply 0% CD for eligible goods.
        # When user explicitly mentions the agreement or certificate, set preferential_cd_rate=0
        if params.get("fta_certificate_type") in ("ACFTA", "ATIGA", "AKFTA", "AJCEP"):
            params["preferential_cd_rate"] = 0

        # Extract quantity if present
        qty_match = re.search(r'(\d+)\s*(?:head|unit|pcs|pieces|kg|liter|meter)', q_lower)
        if qty_match:
            params["quantity"] = float(qty_match.group(1))
            unit_match = re.search(r'(\d+)\s*(\w+)$', qty_match.group(0))
            if unit_match:
                params["unit"] = unit_match.group(2).lower()
        
        # Extract DQ (Discount Quotient / Duty Quota factor)
        # e.g., DQ = 40%, DQ = 0.40, dq 40%
        dq_match = re.search(r'\bdq\s*(?:=\s*)?(\d+(?:\.\d+)?)\s*(%?)', q_lower)
        if dq_match:
            val_str = dq_match.group(1)
            is_pct = dq_match.group(2) == '%'
            try:
                val = float(val_str)
                if is_pct or val > 1.0:
                    val = val / 100.0
                params["dq_factor"] = val
                params["dq_applicable"] = True
            except ValueError:
                pass

        # Extract DV (Declared Value)
        # e.g., DV = 0.00, dv = 120.50, DV 100
        dv_match = re.search(r'\bdv\s*(?:=\s*)?(\d+(?:\.\d+)?)', q_lower)
        if dv_match:
            try:
                params["declared_value"] = float(dv_match.group(1))
            except ValueError:
                pass
        
        # Detect petroleum /vehicle case for specialized taxes (BUR, VVF)
        petroleum_terms = ["petrol", "fuel", "gasoline", "diesel", "petroleum", "oil", "car", "vehicle", "truck","ev"]
        if any(kw in q_lower for kw in petroleum_terms):
            params["petroleum_case"] = True
            
        # 1. Extract Net Mass (e.g. "net mass 100 kg", "net weight 200kg")
        mass_match = re.search(r'(?:net\s+mass\s+)?(\d+(?:\.\d+)?)\s*kg', q_lower)
        if mass_match:
            params["net_mass"] = float(mass_match.group(1))
            
        # 2. Extract Volume (e.g. "Volume 50 liters", "100 L")
        volume_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:l\b|liters?)', q_lower)
        if volume_match:
            params["volume"] = float(volume_match.group(1))
            
        # 3. Auto-detect Petroleum case by HS Code prefix (2710) or keywords
        if (params.get("hs_code") and params["hs_code"].startswith("2710")) or any(
            term in q_lower
            for term in ["petrol", "fuel", "gasoline", "diesel", "petroleum"]):
            params["petroleum_case"] = True

        return params
    
    async def calculate(self, question: str, **kwargs) -> Dict[str, Any]:
        """
        Calculate taxes/duties.
        
        Args:
            question: Calculation question in natural language
            **kwargs: Additional parameters to override extracted values
            
        Returns:
            Calculation results
        """
        from datetime import datetime
        
        logger.info(f"Calling calculator service: {question[:100]}...")
        
        try:
            # Parse question to extract parameters
            parsed = self._parse_question_for_calculation(question)
            parsed.update(kwargs)  # Allow kwargs to override

            # Preserve explicit user currency unless explicitly overridden by kwargs.
            if "currency" in kwargs and kwargs.get("currency"):
                parsed["currency"] = kwargs.get("currency")
            
            # Preserve original CIF value and currency for response formatting
            original_cif_value = parsed.get("cif_value")
            original_currency = parsed.get("currency")
            payload = {
                "question": question,
                "hs_code": parsed.get("hs_code"),
                "cif_value": parsed.get("cif_value"),
                "currency": parsed.get("currency"),
                "origin_country": parsed.get("origin_country"),
                "quantity": parsed.get("quantity"),
                "unit": parsed.get("unit"),
                "fta_applicable": parsed.get("fta_applicable"),
                "fta_certificate_type": parsed.get("fta_certificate_type"),
                "preferential_cd_rate": parsed.get("preferential_cd_rate"),
                "dq_applicable": parsed.get("dq_applicable") or parsed.get("duty_quota_applicable"),
                "dq_factor": parsed.get("dq_factor"),
                "declared_value": parsed.get("declared_value"),
                "net_mass": parsed.get("net_mass"),
                "volume": parsed.get("volume"),
                "petroleum_case": parsed.get("petroleum_case"),
                "rubber_case": parsed.get("rubber_case"),
                "regime": parsed.get("regime", "import"),
                "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            }
            # Clean None values
            payload = {k: v for k, v in payload.items() if v is not None}
            
            logger.info(f"Sending to calculator query: {payload}")
            result = await self._post("query", payload)
            
            # Add original CIF value and currency to response for proper formatting
            result["original_cif_value"] = original_cif_value
            result["original_currency"] = original_currency
            
            logger.info(f"Calculator service returned: total={result.get('total', 'N/A')}, "
                        f"currency={result.get('currency', 'N/A')}")
            return result
        except Exception as e:
            logger.error(f"Calculator service error: {e}")
            raise
    
    async def query(self, question: str, **kwargs) -> Dict[str, Any]:
        """
        Query the calculator service directly with a natural language question.
        """
        logger.info(f"Calling calculator service query endpoint: {question[:100]}...")
        try:
            payload = {"question": question}
            payload.update(kwargs)
            result = await self._post("query", payload)
            logger.info(f"Calculator service returned results")
            return result
        except Exception as e:
            logger.error(f"Calculator service query error: {e}")
            raise

    async def health(self) -> Dict[str, Any]:
        """Check health of calculator service."""
        try:
            result = await self._get("health")
            return result
        except Exception as e:
            logger.error(f"Calculator service health check failed: {e}")
            raise


class TradeDataServiceClient(HttpxServiceClient):
    """Client for trade data service."""
    
    async def query(self, question: str, **kwargs) -> Dict[str, Any]:
        """
        Query trade data.
        
        Args:
            question: Trade query question
            **kwargs: Additional parameters
            
        Returns:
            Trade data query results
        """
        logger.info(f"Calling trade data service: {question[:100]}...")
        
        try:
            payload = {"question": question}
            payload.update(kwargs)
            result = await self._post("query", payload)
            logger.info(f"Trade data service returned results")
            return result
        except Exception as e:
            logger.error(f"Trade data service error: {e}")
            raise
    
    async def health(self) -> Dict[str, Any]:
        """Check health of trade data service."""
        try:
            result = await self._get("health")
            return result
        except Exception as e:
            logger.error(f"Trade data service health check failed: {e}")
            raise


class GeminiLLMClient:
    """
    Gemini-based LLM client for HS code selection and description rewriting.
    Uses Google's Generative AI API for intelligent decision-making.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash", timeout: int = 30):
        """
        Initialize Gemini LLM client.
        
        Args:
            api_key: Google Gemini API key (from env if not provided)
            model: Model name (default: gemini-2.5-flash)
            timeout: Request timeout in seconds
        """
        import os
        
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.timeout = timeout
        self.enabled = bool(self.api_key)
        
        self.client = None
        if self.enabled:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"✓ Gemini LLM Client initialized: {model}")
            except ImportError:
                logger.warning("google-genai not installed, Gemini features disabled")
                self.enabled = False
        else:
            logger.warning("GEMINI_API_KEY not set, Gemini features disabled")
    
    async def select_best_hs_code(
        self, 
        query: str, 
        candidates: list
    ) -> Dict[str, Any]:
        """
        Use Gemini LLM to select the best HS code from candidates.
        
        Args:
            query: User query
            candidates: List of candidate HS codes with metadata
                       [{"hs_code": "87...", "description": "...", "score": 0.95}, ...]
            
        Returns:
            {"selected_code": "87...", "confidence": 0.92, "reason": "...", "index": 0}
        """
        if not self.enabled or not candidates:
            # Fallback to highest score
            if candidates:
                best = max(candidates, key=lambda x: x.get("score", 0))
                return {
                    "selected_code": best.get("hs_code"),
                    "confidence": best.get("score", 0.0),
                    "reason": "Selected by score ranking (LLM unavailable)",
                    "index": candidates.index(best)
                }
            return {"selected_code": None, "confidence": 0.0, "reason": "No candidates", "index": -1}
        
        try:
            # Format candidates for LLM
            candidates_text = "\n".join([
                f"{i+1}. **{c.get('hs_code', 'UNKNOWN')}** - {c.get('description', '')} (score: {c.get('score', 0):.2f})"
                for i, c in enumerate(candidates[:5])  # Top 5
            ])
            
            prompt = f"""You are an expert in HS (Harmonized System) code classification for customs and tariffs.

User Query: "{query}"

Available HS Code Candidates:
{candidates_text}

Your task: Select the SINGLE BEST HS code that matches the user's query most accurately.

Respond with a JSON object (no other text):
{{
  "selected_index": <0-based index of best candidate>,
  "confidence": <0.0-1.0>,
  "reason": "<brief explanation why this is the best match>"
}}"""

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            
            # Parse response
            import json
            import re
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                selected_idx = result.get("selected_index", 0)
                selected_idx = max(0, min(selected_idx, len(candidates) - 1))
                
                selected = candidates[selected_idx]
                return {
                    "selected_code": selected.get("hs_code"),
                    "confidence": float(result.get("confidence", 0.0)),
                    "reason": result.get("reason", "Selected by LLM"),
                    "index": selected_idx
                }
            else:
                # Fallback
                best = max(candidates, key=lambda x: x.get("score", 0))
                return {
                    "selected_code": best.get("hs_code"),
                    "confidence": best.get("score", 0.0),
                    "reason": "LLM response parsing failed, selected by score",
                    "index": candidates.index(best)
                }
        
        except Exception as e:
            logger.error(f"Gemini LLM selection failed: {e}")
            # Fallback to score-based selection
            best = max(candidates, key=lambda x: x.get("score", 0))
            return {
                "selected_code": best.get("hs_code"),
                "confidence": best.get("score", 0.0),
                "reason": f"LLM error: {str(e)}, selected by score",
                "index": candidates.index(best)
            }
    
    async def rewrite_description(self, hs_code: str, technical_description: str) -> str:
        """
        Rewrite technical HS code description to be user-friendly.
        
        Args:
            hs_code: The HS code
            technical_description: Technical description from database
            
        Returns:
            User-friendly description
        """
        if not self.enabled or not technical_description:
            return technical_description
        
        try:
            prompt = f"""Rewrite this technical product description for HS code {hs_code} to be clear and user-friendly for customs/trade professionals. 
Keep it concise (1-2 sentences). Include key distinguishing features.

Technical Description: {technical_description}

Respond with ONLY the user-friendly description, no other text."""

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            return response.text.strip()
        
        except Exception as e:
            logger.warning(f"Description rewrite failed: {e}, using original")
            return technical_description
    
    async def rewrite_descriptions_batch(self, candidates: list) -> list:
        """
        Rewrite descriptions for multiple candidates.
        
        Args:
            candidates: List of {"hs_code": "...", "description": "...", ...}
            
        Returns:
            Same list with rewritten descriptions
        """
        if not self.enabled:
            return candidates
        
        result = []
        for candidate in candidates:
            try:
                hs_code = candidate.get("hs_code", "UNKNOWN")
                original_desc = candidate.get("description", "")
                
                if original_desc:
                    friendly_desc = await self.rewrite_description(hs_code, original_desc)
                    candidate_copy = candidate.copy()
                    candidate_copy["description"] = friendly_desc
                    candidate_copy["original_description"] = original_desc
                    result.append(candidate_copy)
                else:
                    result.append(candidate)
            except Exception as e:
                logger.warning(f"Failed to rewrite description for {hs_code}: {e}")
                result.append(candidate)
        
        return result


class ServiceClientFactory:
    """
    Factory for creating service clients.
    Centralizes client creation and configuration.
    """
    
    @staticmethod
    def create_retrieval_client(base_url: str) -> RetrievalServiceClient:
        """Create retrieval service client."""
        # Retrieval service can take 40+ seconds for HS code lookups (LLM + semantic search + LLM explanation)
        return RetrievalServiceClient(base_url, timeout=50)
    
    @staticmethod
    def create_general_client(base_url: str) -> GeneralServiceClient:
        """Create general ask/generate service client."""
        return GeneralServiceClient(base_url, timeout=50)

    @staticmethod
    def create_calculator_client(base_url: str) -> CalculatorServiceClient:
        """Create calculator service client."""
        # Strip trailing slash if present
        if base_url.endswith("/"):
            base_url = base_url[:-1]
        return CalculatorServiceClient(base_url)
    
    @staticmethod
    def create_trade_data_client(base_url: str) -> TradeDataServiceClient:
        """Create trade data service client."""
        return TradeDataServiceClient(base_url)


class ServiceRegistry:
    """
    Registry of service clients.
    Manages lifecycle and discovery of service clients.
    """
    
    def __init__(self):
        """Initialize service registry."""
        self.clients: Dict[str, BaseServiceClient] = {}
    
    def register(self, name: str, client: BaseServiceClient):
        """Register a service client."""
        self.clients[name] = client
        logger.info(f"Registered service client: {name}")
    
    def get(self, name: str) -> Optional[BaseServiceClient]:
        """Get a registered service client."""
        return self.clients.get(name)
    
    def get_all_clients(self) -> Dict[str, BaseServiceClient]:
        """Get all registered clients."""
        return self.clients.copy()
    
    async def close_all(self):
        """Close all registered clients."""
        for name, client in self.clients.items():
            try:
                if hasattr(client, 'close'):
                    await client.close()
                logger.info(f"Closed service client: {name}")
            except Exception as e:
                logger.error(f"Error closing client {name}: {e}")


# Global service registry instance
_service_registry: Optional[ServiceRegistry] = None


def get_service_registry() -> ServiceRegistry:
    """Get the global service registry."""
    global _service_registry
    if _service_registry is None:
        _service_registry = ServiceRegistry()
    return _service_registry


async def initialize_service_clients(config) -> ServiceRegistry:
    """
    Initialize all service clients from configuration.
    
    Args:
        config: Configuration object
        
    Returns:
        Initialized service registry
    """
    registry = get_service_registry()
    
    # Create and register clients
    if config.retrieval_service_url:
        retrieval_client = ServiceClientFactory.create_retrieval_client(
            config.retrieval_service_url
        )
        registry.register("retrieval", retrieval_client)
    
    if hasattr(config, "general_service_url") and config.general_service_url:
        general_client = ServiceClientFactory.create_general_client(
            config.general_service_url
        )
        registry.register("general", general_client)
    
    if config.calculator_service_url:
        calculator_client = ServiceClientFactory.create_calculator_client(
            config.calculator_service_url
        )
        registry.register("calculator", calculator_client)
    
    if config.trade_data_service_url:
        trade_data_client = ServiceClientFactory.create_trade_data_client(
            config.trade_data_service_url
        )
        registry.register("trade_data", trade_data_client)
    
    return registry
