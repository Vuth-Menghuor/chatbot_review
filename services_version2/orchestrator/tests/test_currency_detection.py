#!/usr/bin/env python
"""
Currency Detection Test Script
Demonstrates MiniLM-based currency detection in the orchestrator
"""

import logging
import sys
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.workflow import WorkflowExecutor


def test_currency_detection():
    """Test currency detection with various questions."""
    
    print("\n" + "="*80)
    print("ORCHESTRATOR CURRENCY DETECTION TEST")
    print("="*80)
    print("\nInitializing WorkflowExecutor with MiniLM currency detector...")
    
    executor = WorkflowExecutor(use_llm_intent=True)
    
    # Test cases organized by expected currency
    test_cases = {
        "USD (Dollar)": [
            "Calculate the import duty and tax on $500 CIF laptop from China",
            "What is the total tax for 1000 USD goods?",
            "How much import tax for $250?",
            "Duty calculation for $1500 from Thailand",
        ],
        "KHR (Khmer Riel) - Default": [
            "Calculate the import tax on 50000 KHR",
            "What is the duty on 100,000 Khmer riel?",
            "Import tax in riel currency",
        ],
        "EUR (Euro)": [
            "Calculate tax on €2000 worth of goods",
            "What is the duty on 1500 EUR?",
            "Import tax for €500 laptop",
        ],
        "THB (Thai Baht)": [
            "Calculate tax on 5000 THB",
            "What is the duty on Thai baht?",
            "Import tax for 10000 baht from Thailand",
        ],
        "Unclear/No Currency": [
            "Calculate the import tax",
            "What is the duty on imported goods?",
            "Import tax rate?",
        ],
    }
    
    print("\n" + "-"*80)
    print("CURRENCY DETECTION RESULTS")
    print("-"*80)
    
    for category, questions in test_cases.items():
        print(f"\n📌 {category}")
        print("-" * 40)
        
        for question in questions:
            # Detect currency
            detected_currency, confidence = executor.detect_currency(
                question,
                confidence_threshold=0.6
            )
            
            # Determine confidence level
            if confidence >= 0.75:
                confidence_level = "🟢 HIGH"
            elif confidence >= 0.6:
                confidence_level = "🟡 MODERATE"
            else:
                confidence_level = "🔴 LOW (using default)"
            
            print(f"\n  Question: {question[:70]}...")
            print(f"  └─ Currency: {detected_currency}")
            print(f"     Confidence: {confidence:.3f} {confidence_level}")
    
    print("\n" + "="*80)
    print("CURRENCY DETECTION LOGIC SUMMARY")
    print("="*80)
    print("""
    Layer 1: MiniLM Semantic Similarity
    ├─ Uses sentence embeddings for semantic understanding
    ├─ Compares question against currency keyword patterns
    └─ Returns confidence score (0.0-1.0)

    Layer 2: Default Fallback
    ├─ If confidence < 0.6: Use KHR (Khmer Riel) as default
    ├─ If currency detection fails: Use KHR
    └─ User can override in clarification round

    Supported Currencies:
    ✓ USD (Dollar) - Patterns: $, USD, dollar, greenback
    ✓ KHR (Riel) - Patterns: KHR, riel, Khmer riel
    ✓ EUR (Euro) - Patterns: €, EUR, euro
    ✓ THB (Thai Baht) - Patterns: THB, baht, Thai baht
    ✓ CNY (Yuan/RMB) - Patterns: CNY, yuan, RMB
    ✓ VND (Dong) - Patterns: VND, dong, Vietnamese
    ✓ GBP (Pound) - Patterns: GBP, pound, £
    ✓ JPY (Yen) - Patterns: JPY, yen, Japanese

    Integration with Calculator:
    ├─ Currency extracted during CALCULATION intent
    ├─ Passed to calculator service as override parameter
    └─ Ensures accurate duty/tax calculations
    """)
    
    print("\n" + "="*80)
    print("WORKFLOW INTEGRATION")
    print("="*80)
    print("""
    1. Query Received by Orchestrator
       "Calculate tax on $500 from China"
    
    2. Intent Detection (LLM or Keyword)
       → Detected Intent: CALCULATION
    
    3. Currency Detection (MiniLM)
       → Detected Currency: USD (confidence: 0.92)
    
    4. Validation & Clarification
       → If confidence >= 0.6: Proceed
       → If confidence < 0.6: Request clarification
    
    5. Call Calculator Service
       → calculator.calculate(question, currency="USD")
       → Returns: duty, tax, total, exchange_rate, etc.
    
    6. Format Response
       → Include detected currency in explanation
       → Show step-by-step calculation
    """)
    
    print("="*80 + "\n")


if __name__ == "__main__":
    try:
        test_currency_detection()
        print("✅ Currency detection test completed successfully!")
    except Exception as e:
        print(f"\n❌ Error during currency detection test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
