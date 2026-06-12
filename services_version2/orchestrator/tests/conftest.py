"""
Test fixtures and utilities
Includes visual formatting for prettier test output
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock
from pathlib import Path
import os
import sys
import importlib
from dotenv import load_dotenv

# Load orchestrator service .env for tests globally
orchestrator_env = Path(__file__).resolve().parents[1] / ".env"
if orchestrator_env.exists():
    load_dotenv(orchestrator_env)
else:
    load_dotenv()

# Ensure orchestrator package modules are importable under both their
# full package names and short names used by some legacy tests (e.g. "core", "infrastructure").
# This keeps the v2 orchestrator workflow intact while allowing tests
# that import bare module names to run in the test environment.
try:
    repo_root = Path(__file__).resolve().parents[2].parent  # repo root
    services_pkg = Path(__file__).resolve().parents[1]  # orchestrator dir
    # Add repo root to sys.path so `services_version2` package is importable
    sys.path.insert(0, str(repo_root))
    base_pkg = "services_version2.orchestrator"
    for short in ("core", "infrastructure", "api", "config"):
        try:
            mod = importlib.import_module(f"{base_pkg}.{short}")
            # register short name in sys.modules so `import core` works
            sys.modules[short] = mod
        except Exception:
            # Best-effort mapping; tests that don't need the module will continue
            pass
except Exception:
    pass

from ..config import OrchestratorConfig, reset_config
from ..core import ServiceCoordinator, WorkflowExecutor, get_policy_engine
from ..infrastructure import (
    RetrievalServiceClient,
    CalculatorServiceClient,
    TradeDataServiceClient,
)


# ==================== VISUAL FORMATTING ====================

class ColorCodes:
    """Terminal color codes."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'
    DIM = '\033[2m'


class VisualTestPlugin:
    """Custom pytest plugin for visual test output."""
    
    def __init__(self):
        self.test_count = 0
        self.passed_count = 0
        self.failed_count = 0
        self.current_class = None
        self.class_stats = {}
    
    def pytest_sessionstart(self, session):
        """Print session header."""
        print(f"\n{ColorCodes.BOLD}{ColorCodes.CYAN}")
        print("=" * 80)
        print("RETRY LOGIC TEST SUITE".center(80))
        print("Testing Exponential Backoff Implementation".center(80))
        print("=" * 80)
        print(f"{ColorCodes.END}\n")
    
    def pytest_runtest_logstart(self, nodeid, location):
        """Called before test execution starts."""
        parts = nodeid.split("::")
        if len(parts) >= 2:
            test_class = parts[1]
            test_name = parts[2] if len(parts) > 2 else "test"
            
            if self.current_class != test_class:
                self.current_class = test_class
                if test_class not in self.class_stats:
                    self.class_stats[test_class] = {"passed": 0, "failed": 0}
                print(f"\n{ColorCodes.BOLD}{ColorCodes.BLUE}[{test_class}]{ColorCodes.END}")
    
    def pytest_runtest_logreport(self, report):
        """Called after each test execution."""
        if report.when == "call":
            nodeid = report.nodeid
            parts = nodeid.split("::")
            test_class = parts[1] if len(parts) > 1 else "Unknown"
            test_name = parts[2] if len(parts) > 2 else "test"
            
            if test_class not in self.class_stats:
                self.class_stats[test_class] = {"passed": 0, "failed": 0}
            
            if report.passed:
                self.passed_count += 1
                self.class_stats[test_class]["passed"] += 1
                # Shorten test name for display
                display_name = test_name.replace("test_", "").replace("_", " ").title()
                print(f"  {ColorCodes.GREEN}[PASS]{ColorCodes.END} {display_name}")
            else:
                self.failed_count += 1
                self.class_stats[test_class]["failed"] += 1
                display_name = test_name.replace("test_", "").replace("_", " ").title()
                print(f"  {ColorCodes.RED}[FAIL]{ColorCodes.END} {display_name}")
    
    def pytest_sessionfinish(self, session, exitstatus):
        """Print session summary."""
        total = self.passed_count + self.failed_count
        
        print(f"\n{ColorCodes.BOLD}{ColorCodes.CYAN}")
        print("=" * 80)
        
        if self.failed_count == 0:
            status = f"{ColorCodes.GREEN}✓ ALL TESTS PASSED{ColorCodes.CYAN}"
        else:
            status = f"{ColorCodes.RED}✗ SOME TESTS FAILED{ColorCodes.CYAN}"
        
        print(status.center(80))
        print("=" * 80)
        
        # Summary line
        summary = f"{self.passed_count}/{total} tests passed"
        if self.failed_count > 0:
            summary += f" | {self.failed_count} failed"
        print(f"\n{summary}")
        
        # Class breakdown
        print(f"\n{ColorCodes.YELLOW}Test Results Breakdown:{ColorCodes.END}")
        for cls_name, stats in self.class_stats.items():
            passed = stats["passed"]
            failed = stats["failed"]
            total_cls = passed + failed
            cls_display = cls_name.replace("Test", "").replace("Retry", "").replace("Logic", "")
            if failed > 0:
                result = f"{ColorCodes.RED}{passed}/{total_cls} passed ({failed} failed){ColorCodes.END}"
            else:
                result = f"{ColorCodes.GREEN}{passed}/{total_cls} passed{ColorCodes.END}"
            print(f"  • {cls_display}: {result}")
        
        print(f"\n{ColorCodes.BOLD}{ColorCodes.CYAN}{'=' * 80}{ColorCodes.END}\n")


# Register the plugin
def pytest_configure(config):
    """Register the visual plugin."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
    plugin = VisualTestPlugin()
    config.pluginmanager.register(plugin, "visual-plugin")


@pytest.fixture
def config():
    """Provide test configuration."""
    reset_config()
    return OrchestratorConfig()


@pytest.fixture
def mock_retrieval_client():
    """Provide mock retrieval client."""
    client = AsyncMock(spec=RetrievalServiceClient)
    base_response = {
        "documents": [
            {
                "doc_id": "test_1",
                "title": "Test Document",
                "content": "Test content",
                "score": 0.95
            }
        ],
        "status": "success",
        "answer_source": "mock",
        "final_answer": "Mocked retrieval answer"
    }

    client.retrieve = AsyncMock(return_value=base_response)
    client.definition = AsyncMock(return_value=base_response)
    client.policy_inquiry = AsyncMock(return_value=base_response)
    client.general = AsyncMock(return_value=base_response)
    client.hs_code_lookup = AsyncMock(return_value=base_response)
    return client


@pytest.fixture
def mock_calculator_client():
    """Provide mock calculator client."""
    client = AsyncMock(spec=CalculatorServiceClient)
    client.calculate = AsyncMock(return_value={
        "result": {
            "customs_duty": 100.0,
            "special_tax": 50.0,
            "vat": 75.0
        },
        "total_tax": 225.0
    })
    client.query = AsyncMock(return_value={
        "total": 225.0,
        "currency": "KHR",
        "breakdown": {
            "cif_value": 402200.0,
            "cop_amount": 100.0,
            "sop_amount": 50.0,
            "vop_amount": 75.0,
            "fees": 0.0
        },
        "line_items": [
            {
                "name": "Import Taxes (COP)",
                "tax_type": "CD",
                "amount": 100.0,
                "currency": "KHR",
                "base": 402200.0,
                "rate": 15.0
            }
        ],
        "assumptions": ["Mocked calculation"],
        "references": []
    })
    return client


@pytest.fixture
def mock_trade_data_client():
    """Provide mock trade data client."""
    client = AsyncMock(spec=TradeDataServiceClient)
    client.query = AsyncMock(return_value={
        "data": [
            {
                "country": "Vietnam",
                "value": 1000000,
                "year": 2024
            }
        ]
    })
    return client


class DummyLLMService:
    def __init__(self, intent="definition", selection=None):
        self.intent = intent
        self.selection = selection or {
            "selected_code": None,
            "confidence": 0.0,
            "reason": "No selection",
            "index": -1,
        }

    def classify_intent(self, question):
        return self.intent, 0.95, "test intent"

    async def select_best_hs_code(self, query, candidates):
        return self.selection

    async def rewrite_descriptions_batch(self, candidates):
        return candidates

    async def rewrite_input(self, user_input, context=None, intent_hint=None):
        return user_input, {
            "rewrite_reason": "not_needed",
            "confidence": 1.0,
            "rewritten": False,
        }

    async def extract_trade_parameters(self, question):
        return {}

    def is_available(self) -> bool:
        return True


@pytest.fixture
def coordinator(mock_retrieval_client, mock_calculator_client, mock_trade_data_client):
    """Provide service coordinator with mocked clients."""
    policy_engine = get_policy_engine()
    formatter_mock = MagicMock()
    formatter_mock.is_available = MagicMock(return_value=False)
    return ServiceCoordinator(
        retrieval_client=mock_retrieval_client,
        calculator_client=mock_calculator_client,
        trade_data_client=mock_trade_data_client,
        policy_engine=policy_engine,
        use_llm_intent=False,
        use_input_rewriter=False,
        llm_service=None,
        formatter_service=formatter_mock,
    )


@pytest.fixture
def event_loop():
    """Provide event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
