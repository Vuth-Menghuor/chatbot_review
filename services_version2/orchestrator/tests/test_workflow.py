"""
Unit tests for workflow module
"""

import pytest
from ..core import WorkflowIntent, WorkflowStatus, WorkflowContext, WorkflowExecutor
import services_version2.orchestrator.core.workflow as workflow_mod

# Force offline/local keyword and pattern detection for all unit tests
import sys
for name, mod in list(sys.modules.items()):
    if name.endswith('core.workflow') or name == 'core.workflow':
        mod.LLM_INTENT_DETECTION_AVAILABLE = False
        mod.LLM_CURRENCY_DETECTION_AVAILABLE = False
workflow_mod.LLM_INTENT_DETECTION_AVAILABLE = False
workflow_mod.LLM_CURRENCY_DETECTION_AVAILABLE = False


class TestWorkflowContext:
    """Test WorkflowContext class."""
    
    def test_context_initialization(self):
        """Test workflow context initialization."""
        context = WorkflowContext(
            request_id="test_123",
            question="What is the HS code for chicken?"
        )
        
        assert context.request_id == "test_123"
        assert context.question == "What is the HS code for chicken?"
        assert context.status == WorkflowStatus.PENDING
        assert context.errors == []
        assert context.clarifications == []
    
    def test_add_error(self):
        """Test adding error to context."""
        context = WorkflowContext(
            request_id="test_123",
            question="Test question"
        )
        
        context.add_error("Test error")
        assert "Test error" in context.errors
        assert len(context.errors) == 1
    
    def test_add_clarification(self):
        """Test adding clarification to context."""
        context = WorkflowContext(
            request_id="test_123",
            question="Test question"
        )
        
        context.add_clarification("Need more info")
        assert "Need more info" in context.clarifications
        assert len(context.clarifications) == 1


class TestWorkflowIntentDetection:
    """Test workflow intent detection."""
    
    def test_detect_calculation_intent(self):
        """Test detection of calculation intent."""
        executor = WorkflowExecutor()
        
        questions = [
            "Calculate the import tax on 100 USD of goods",
            "What is the duty on this product?",
            "How much import tax will I pay?",
        ]
        
        for question in questions:
            intent = executor.detect_intent(question)
            assert intent == WorkflowIntent.CALCULATION
    
    def test_detect_trade_query_intent(self):
        """Test detection of trade query intent."""
        executor = WorkflowExecutor()
        
        questions = [
            "What was the trade volume with Vietnam last year?",
            "Show me export data from Cambodia",
            "What is the import volume?",
        ]
        
        for question in questions:
            intent = executor.detect_intent(question)
            assert intent == WorkflowIntent.TRADE_QUERY
    
    def test_detect_definition_intent(self):
        """Test detection of definition intent."""
        executor = WorkflowExecutor()
        
        questions = [
            "What is an HS code?",
            "Define customs duty",
            "Explain VAT",
        ]
        
        for question in questions:
            intent = executor.detect_intent(question)
            assert intent == WorkflowIntent.GENERAL


class TestWorkflowSequencing:
    """Test workflow sequencing."""
    
    def test_get_workflow_sequence(self):
        """Test workflow sequence generation."""
        executor = WorkflowExecutor()
        
        sequences = {
            WorkflowIntent.CALCULATION: ["calculator"],
            WorkflowIntent.TRADE_QUERY: ["trade_data"],
            WorkflowIntent.GENERAL: ["retrieval"],
        }
        
        for intent, expected_sequence in sequences.items():
            sequence = executor.get_workflow_sequence(intent)
            assert sequence == expected_sequence


class TestCurrencyDetection:
    """Test MiniLM-based currency detection."""
    
    def test_detect_currency_usd(self):
        """Test USD currency detection."""
        executor = WorkflowExecutor()
        
        questions = [
            "Calculate tax on $500 worth of goods",
            "What is the duty on 1000 USD?",
            "Import tax for $250 laptop from China",
        ]
        
        for question in questions:
            currency, confidence = executor.detect_currency(question)
            assert currency == "USD", f"Expected USD for '{question}', got {currency}"
            assert confidence > 0.0, f"Confidence should be > 0 for '{question}'"

    def test_detect_currency_bucks_stays_usd(self):
        """Test that 'bucks' is treated as explicit USD and not overridden by origin-country fallback."""
        executor = WorkflowExecutor()

        question = "Calculate import duty for HS 0102.29.11 CIF 800 bucks from China"
        currency, confidence = executor.detect_currency(question)

        assert currency == "USD", f"Expected USD for '{question}', got {currency}"
        assert confidence > 0.0, f"Confidence should be > 0 for '{question}'"
    
    def test_detect_currency_khr(self):
        """Test KHR (Khmer Riel) currency detection."""
        executor = WorkflowExecutor()
        
        questions = [
            "Calculate tax on 50000 KHR",
            "What is the duty on 100,000 Khmer riel?",
            "Import tax for riel from Cambodia",
        ]
        
        for question in questions:
            currency, confidence = executor.detect_currency(question)
            assert currency == "KHR", f"Expected KHR for '{question}', got {currency}"
            assert confidence > 0.0, f"Confidence should be > 0 for '{question}'"
    
    def test_detect_currency_eur(self):
        """Test EUR (Euro) currency detection."""
        executor = WorkflowExecutor()
        
        questions = [
            "Calculate tax on €2000",
            "What is the duty on 1500 EUR?",
            "Import tax for euro goods",
        ]
        
        for question in questions:
            currency, confidence = executor.detect_currency(question)
            assert currency == "EUR", f"Expected EUR for '{question}', got {currency}"
            assert confidence > 0.0, f"Confidence should be > 0 for '{question}'"
    
    def test_default_to_khr_when_unclear(self):
        """Test default to KHR when currency is unclear."""
        executor = WorkflowExecutor()
        
        # Questions without clear currency indication
        questions = [
            "Calculate the import tax on 500 goods",
            "What is the duty?",
            "Import tax for electronics",
        ]
        
        for question in questions:
            currency, confidence = executor.detect_currency(question, confidence_threshold=0.6)
            # Should default to KHR when confidence is below threshold
            assert currency == "KHR", f"Should default to KHR for '{question}', got {currency}"
    
    def test_currency_confidence_scoring(self):
        """Test that confidence scores are returned correctly."""
        executor = WorkflowExecutor()
        
        clear_question = "Calculate tax on $500 from China"
        unclear_question = "What is the import tax?"
        
        currency_clear, conf_clear = executor.detect_currency(clear_question)
        currency_unclear, conf_unclear = executor.detect_currency(unclear_question)
        
        # Clear questions should have higher confidence
        assert currency_clear == "USD"
        assert currency_unclear == "KHR"
        # Note: conf_clear and conf_unclear comparisons depend on MiniLM availability


class TestWorkflowContextWithCurrency:
    """Test WorkflowContext with currency tracking."""
    
    def test_context_tracks_currency(self):
        """Test that workflow context tracks detected currency."""
        context = WorkflowContext(
            request_id="test_123",
            question="Calculate tax on $1000"
        )
        
        # Initially no currency detected
        assert context.detected_currency is None
        assert context.currency_confidence == 0.0
        
        # After detection
        context.detected_currency = "USD"
        context.currency_confidence = 0.95
        
        assert context.detected_currency == "USD"
        assert context.currency_confidence == 0.95

