"""
Demo Script: Input Rewriting Layer
Shows multi-turn conversation with context awareness using local llama3.2:3b
"""

import asyncio
import logging
import json
from typing import Optional
import sys
import os

# Add workspace root to sys.path for imports
demo_dir = os.path.dirname(os.path.abspath(__file__))
services_v2_dir = os.path.dirname(demo_dir)
workspace_root = os.path.dirname(services_v2_dir)
sys.path.insert(0, workspace_root)

# Setup logging - minimal to avoid clutter
logging.basicConfig(
    level=logging.WARNING,  # Suppress info logs
    format='%(message)s'
)

# Import from orchestrator with absolute path
from services_version2.orchestrator.core.input_rewriter import (
    InputRewriter,
    SessionManager,
    SessionContext,
    Topic
)
import httpx
import time

# Color codes for better visualization
HEADER = '\033[95m'
BLUE = '\033[94m'
CYAN = '\033[96m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BOLD = '\033[1m'
UNDERLINE = '\033[4m'
END = '\033[0m'


def print_header(text):
    """Print a section header."""
    print(f"\n{BOLD}{CYAN}╔{'='*68}╗{END}")
    print(f"{BOLD}{CYAN}║ {text.ljust(66)} ║{END}")
    print(f"{BOLD}{CYAN}╚{'='*68}╝{END}\n")


def print_subheader(text):
    """Print a subsection header."""
    print(f"\n{BOLD}{BLUE}{'─'*70}{END}")
    print(f"{BOLD}{BLUE}■ {text}{END}")
    print(f"{BOLD}{BLUE}{'─'*70}{END}\n")


def print_box(title, content_dict):
    """Print a nicely formatted box with content."""
    max_len = max(len(k) for k in content_dict.keys()) + 1
    
    print(f"{YELLOW}┌{'─'*(68)}┐{END}")
    print(f"{YELLOW}│ {BOLD}{title}{END}{YELLOW}{' '*max(1, 66-len(title))}│{END}")
    print(f"{YELLOW}├{'─'*(68)}┤{END}")
    
    for key, value in content_dict.items():
        key_str = f"{key}:".ljust(max_len)
        if isinstance(value, bool):
            val_str = f"{GREEN}✓ Yes{END}" if value else f"{RED}✗ No{END}"
        elif isinstance(value, (int, float)):
            val_str = f"{CYAN}{value}{END}"
        else:
            val_str = f"{value}"
        print(f"{YELLOW}│ {END}{BOLD}{key_str}{END} {val_str}{' '*max(0, 50-len(str(value)))} {YELLOW}│{END}")
    
    print(f"{YELLOW}└{'─'*(68)}┘{END}\n")


def print_comparison(original, rewritten):
    """Print a visual comparison of original vs rewritten."""
    print(f"{RED}ORIGINAL:{END}")
    print(f"{RED}  \"{original}\"{END}")
    print()
    print(f"{GREEN}REWRITTEN:{END}")
    print(f"{GREEN}  \"{rewritten}\"{END}")
    if original.lower() != rewritten.lower():
        print(f"\n{BOLD}{CYAN}✨ INPUT EXPANDED WITH CONTEXT!{END}")
    print()


def print_step(step_num, step_name):
    """Print a numbered step."""
    print(f"{BOLD}[Step {step_num}] {CYAN}{step_name}{END}")


class DemoOrchestrator:
    """
    Simplified orchestrator for demo purposes.
    Shows input rewriting layer in action with real Ollama calls.
    """
    
    def __init__(self, ollama_host: str = "http://localhost:11434", model: str = "llama3.2:3b"):
        """Initialize demo orchestrator."""
        self.rewriter = None
        self.session_manager = SessionManager()
        self.ollama_host = ollama_host
        self.model = model
    
    async def _verify_ollama(self) -> bool:
        """Verify Ollama is running and model is available."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                # Test 1: Check if Ollama is running
                print(f"{CYAN}   Testing connection to {self.ollama_host}...{END}")
                response = await client.get(f"{self.ollama_host}/api/tags")
                response.raise_for_status()
                
                models = response.json().get("models", [])
                model_names = [m.get("name") for m in models]
                
                # Test 2: Check if llama3.2:3b is available
                if any(self.model in name for name in model_names):
                    print(f"{GREEN}✓ Ollama running at {self.ollama_host}{END}")
                    print(f"{GREEN}✓ Model {self.model} available{END}")
                    return True
                else:
                    print(f"{RED}✗ Model {self.model} not found!{END}")
                    print(f"   Available models: {', '.join(model_names) if model_names else 'None'}")
                    print(f"   {YELLOW}Run: ollama pull {self.model}{END}")
                    return False
        except Exception as e:
            print(f"{RED}✗ Cannot connect to Ollama at {self.ollama_host}{END}")
            print(f"   Error: {e}")
            print(f"   {YELLOW}Make sure Ollama is running: ollama serve{END}")
            return False
    
    async def initialize(self):
        """Initialize input rewriter with real Ollama connection."""
        print(f"\n{YELLOW}🔧 Setting up Ollama connection...{END}")
        
        # Verify Ollama first
        if not await self._verify_ollama():
            raise Exception("Ollama not available or model not loaded")
        
        try:
            self.rewriter = InputRewriter(
                ollama_host=self.ollama_host,
                model=self.model
            )
            print(f"{GREEN}✓ InputRewriter ready for REAL Ollama calls{END}\n")
        except Exception as e:
            print(f"{RED}✗ Failed to initialize rewriter: {e}{END}")
            raise
    
    async def process_query(
        self,
        question: str,
        session_id: str,
        turn_number: int = 1
    ) -> dict:
        """Process a query with input rewriting - matches orchestrator 5-step flow."""
        
        # Show input
        print(f"\n{BOLD}{CYAN}TURN {turn_number}{END}\n")
        print(f"{YELLOW}📥 User Input:{END}")
        print(f"   {BOLD}\"{question}\"{END}\n")
        
        # ===== STEP 1: GET SESSION CONTEXT =====
        print_step(1, "Get Session Context")
        session = self.session_manager.get_or_create_session(session_id)
        
        print(f"{YELLOW}📍 Session Context:{END}")
        context_dict = {
            "Topic": session.current_topic.value if session.current_topic else "—",
            "Mode": session.import_export_mode or "—",
            "Product": session.product_category or "—",
            "Currency": session.currency or "—",
            "History": f"{len(session.turns)} turn(s)"
        }
        for key, val in context_dict.items():
            print(f"   {key}: {CYAN}{val}{END}")
        print(f"{GREEN}✓ Session retrieved{END}\n")
        
        # ===== STEP 2: REWRITE INPUT (WITH LLM) =====
        print_step(2, "Rewrite Input (using LLM)")
        try:
            rewritten, metadata = await self.rewriter.rewrite_input(
                question,
                context=session
            )
            
            changed = question.lower() != rewritten.lower()
            if changed:
                print(f"{GREEN}✓ Rewritten:{END}\n")
                print_comparison(question, rewritten)
            else:
                print(f"{CYAN}ℹ No rewriting needed (first turn){END}\n")
                print(f"   {question}\n")
            
            # Show rewrite details
            details = {
                "Reason": metadata.get('rewrite_reason', 'unknown'),
                "Confidence": f"{metadata.get('confidence', 0):.1%}",
                "Intent Changed": metadata.get('intent_changed', False),
            }
            if metadata.get('topic_switch'):
                details["Topic Switch"] = True
            
            print_box("Rewrite Details", details)
            
        except Exception as e:
            print(f"{RED}✗ Rewrite failed: {e}{END}\n")
            rewritten = question
            metadata = {"error": str(e)}
        
        # ===== STEP 3: DETECT INTENT (2-LAYER SYSTEM) =====
        print_step(3, "Detect Intent (LLM + Keyword Fallback)")
        # In real orchestrator, this uses: WorkflowExecutor.detect_intent()
        # For demo, we simulate the 2-layer system:
        # Layer 1: Try keyword detection (simplified version of LLM)
        if "import" in rewritten.lower():
            detected_intent = "import"
            detection_layer = "Layer 1 (Keywords)"
        elif "export" in rewritten.lower():
            detected_intent = "export"
            detection_layer = "Layer 1 (Keywords)"
        else:
            detected_intent = "unknown"
            detection_layer = "Layer 2 (Fallback)"
        
        intent_box = {
            "Detected Intent": f"{CYAN}{detected_intent.upper()}{END}",
            "Detection Layer": f"{CYAN}{detection_layer}{END}",
            "Confidence": f"{CYAN}High{END}" if detected_intent != "unknown" else f"{RED}Low{END}"
        }
        print_box("Intent Detection Result", intent_box)
        print()
        
        # ===== STEP 4: ROUTE TO SERVICE =====
        print_step(4, "Route to Service")
        service_mapping = {
            "import": "Calculator Service",
            "export": "Calculator Service",
            "unknown": "Definition Service (fallback)"
        }
        selected_service = service_mapping.get(detected_intent, "Definition Service")
        print(f"{GREEN}✓ Routing to: {BOLD}{selected_service}{END}")
        print(f"   (Simulated service call...)\n")
        mock_response = f"Duty and tax information for your {detected_intent} query."
        
        # ===== STEP 5: UPDATE SESSION CONTEXT =====
        print_step(5, "Update Session Context")
        if detected_intent != "unknown":
            self.session_manager.update_session_context(
                session_id,
                import_export_mode=detected_intent
            )
            print(f"{GREEN}✓ Session updated: mode = {CYAN}{detected_intent}{END}")
        
        # Record turn in history
        session.add_turn(question, mock_response)
        print(f"{GREEN}✓ Turn recorded in history (total: {len(session.turns)} turn(s)){END}\n")
        
        return {
            "original_input": question,
            "rewritten_input": rewritten,
            "detected_intent": detected_intent,
            "detection_layer": detection_layer,
            "selected_service": selected_service,
            "rewrite_metadata": metadata,
            "session_state": {
                "id": session_id,
                "topic": str(session.current_topic),
                "mode": session.import_export_mode,
                "product": session.product_category,
                "turns": len(session.turns)
            }
        }
    
    async def close(self):
        """Close connections."""
        if self.rewriter:
            await self.rewriter.close()


async def demo_scenario_1():
    """
    Scenario 1: Simple Import Query (No Rewriting Needed)
    Expected: First turn has no previous context, so input used as-is
    """
    print_header("SCENARIO 1: Simple Query (First Turn)")
    print(f"{BOLD}{YELLOW}📌 Expected Behavior:{END}")
    print(f"   First turn → No context → Input used as-is\n")
    
    orchestrator = DemoOrchestrator()
    await orchestrator.initialize()
    
    result = await orchestrator.process_query(
        question="How much import duty on rice?",
        session_id="user_alice_session_001",
        turn_number=1
    )
    
    print(f"{BOLD}{CYAN}SUMMARY:{END}")
    summary = {
        "Input Changed": result['original_input'] != result['rewritten_input'],
        "Detected Intent": f"{CYAN}{result['detected_intent']}{END}",
        "Detection Layer": f"{CYAN}{result['detection_layer']}{END}",
        "Service Routed To": f"{CYAN}{result['selected_service']}{END}"
    }
    print_box("Turn 1 Summary", summary)
    
    await orchestrator.close()


async def demo_scenario_2():
    """
    Scenario 2: Multi-Turn Conversation with Mode Switch
    Expected: 
    - Turn 1: Import rice → stores context
    - Turn 2: "how about export?" → rewritten to include rice + export
    """
    print_header("SCENARIO 2: Mode Switch (Import → Export)")
    print(f"{BOLD}{YELLOW}📌 Expected Behavior:{END}")
    print(f"   Turn 1: Store rice + import context")
    print(f"   Turn 2: Ambiguous \"how about export?\" → Expanded!\n")
    
    orchestrator = DemoOrchestrator()
    await orchestrator.initialize()
    
    print_subheader("Turn 1: Establish Import Context")
    result1 = await orchestrator.process_query(
        question="What is the duty rate for importing rice from Thailand?",
        session_id="user_bob_session_002",
        turn_number=1
    )
    
    # Update session with detected context (simulating result from Step 5)
    orchestrator.session_manager.update_session_context(
        "user_bob_session_002",
        import_export_mode="import",
        product_category="rice"
    )
    print(f"{GREEN}✓ Step 5 Completed: Session Context Updated{END}")
    print(f"   Product: {CYAN}rice{END}")
    print(f"   Mode: {CYAN}import{END}\n")
    
    print_subheader("Turn 2: Ambiguous Follow-Up (Should Expand)")
    result2 = await orchestrator.process_query(
        question="How about export?",
        session_id="user_bob_session_002",
        turn_number=2
    )
    
    print(f"{BOLD}{CYAN}ANALYSIS:{END}")
    analysis = {
        "Intent Changed": result2['rewrite_metadata'].get('intent_changed', False),
        "Change Reason": result2['rewrite_metadata'].get('rewrite_reason', 'none'),
        "New Intent Detected": f"{CYAN}{result2['detected_intent']}{END}",
        "Service Routed": f"{CYAN}{result2['selected_service']}{END}",
        "Input Expanded": result2['original_input'] != result2['rewritten_input']
    }
    print_box("Turn 2 Analysis", analysis)
    
    await orchestrator.close()


async def demo_scenario_3():
    """
    Scenario 3: Product Category Tracking
    Expected:
    - Turn 1: "electronics" mentioned
    - Turn 2: "What's the tax?" → rewritten to include electronics
    """
    print_header("SCENARIO 3: Product Category Tracking")
    print(f"{BOLD}{YELLOW}📌 Expected Behavior:{END}")
    print(f"   Turn 1: Mention electronics")
    print(f"   Turn 2: Ambiguous question → Context preserved\n")
    
    orchestrator = DemoOrchestrator()
    await orchestrator.initialize()
    
    print_subheader("Turn 1: Mention Electronics Product")
    result1 = await orchestrator.process_query(
        question="What's the import tax on electronics from China?",
        session_id="user_charlie_session_003",
        turn_number=1
    )
    
    # Update session with product (simulating result from Step 5)
    orchestrator.session_manager.update_session_context(
        "user_charlie_session_003",
        product_category="electronics",
        import_export_mode="import"
    )
    print(f"{GREEN}✓ Step 5 Completed: Session Context Updated{END}")
    print(f"   Product: {CYAN}electronics{END}")
    print(f"   Mode: {CYAN}import{END}\n")
    
    print_subheader("Turn 2: Generic Question (Should Reuse Context)")
    result2 = await orchestrator.process_query(
        question="What if the value is higher?",
        session_id="user_charlie_session_003",
        turn_number=2
    )
    
    print(f"{BOLD}{CYAN}CONTEXT PRESERVATION:{END}")
    session = orchestrator.session_manager.get_or_create_session("user_charlie_session_003")
    preservation = {
        "Product Retained": session.product_category or "—",
        "Mode Retained": session.import_export_mode or "—",
        "Conversation Turns": f"{len(session.turns)}"
    }
    print_box("Session State", preservation)
    
    await orchestrator.close()


async def demo_scenario_4():
    """
    Scenario 4: Long Conversation (Token Management)
    Expected:
    - Multiple turns (5 questions)
    - SessionContext keeps only last N turns
    - Prevents token bloat
    """
    print_header("SCENARIO 4: Long Conversation (Token Management)")
    print(f"{BOLD}{YELLOW}📌 Expected Behavior:{END}")
    print(f"   Multiple turns → History limited to keep only recent ones")
    print(f"   Memory efficient for long conversations\n")
    
    orchestrator = DemoOrchestrator()
    await orchestrator.initialize()
    
    session_id = "user_diana_session_004"
    questions = [
        ("What's the duty on coffee?", "coffee", "import"),
        ("How about tea?", "tea", "import"),
        ("What if I export coffee?", "coffee", "export"),
        ("And for tea?", "tea", "export"),
        ("Any other products?", None, "export"),
    ]
    
    print(f"{BOLD}{CYAN}Processing 5 Turns...{END}\n")
    
    for turn, (question, product, mode) in enumerate(questions, 1):
        print_subheader(f"Turn {turn}")
        
        result = await orchestrator.process_query(
            question=question,
            session_id=session_id,
            turn_number=turn
        )
        
        if product:
            orchestrator.session_manager.update_session_context(
                session_id,
                product_category=product,
                import_export_mode=mode
            )
        
        session = orchestrator.session_manager.get_or_create_session(session_id)
        print(f"{CYAN}📊 History State: {len(session.turns)}/{session.max_turns} turns stored (memory efficient){END}\n")
    
    print(f"{BOLD}{CYAN}FINAL SUMMARY:{END}")
    session = orchestrator.session_manager.get_or_create_session(session_id)
    summary = {
        "Total Turns Processed": "5",
        "Turns Stored in History": f"{len(session.turns)}",
        "Max Turns Kept": f"{session.max_turns}",
        "Token Efficiency": "✓ Optimized (only recent turns)"
    }
    print_box("Conversation Summary", summary)
    
    await orchestrator.close()


async def main():
    """Run all demo scenarios."""
    print(f"\n{BOLD}{HEADER}")
    print("╔" + "═"*68 + "╗")
    print("║" + " "*68 + "║")
    print("║  INPUT REWRITING LAYER - INTERACTIVE DEMO".center(68) + "║")
    print("║  💻 USING REAL LOCAL OLLAMA (llama3.2:3b)".center(68) + "║")
    print("║" + " "*68 + "║")
    print("╚" + "═"*68 + "╝")
    print(f"{END}\n")
    
    print(f"{BOLD}{YELLOW}⚠️  SETUP REQUIRED:{END}")
    print(f"   {CYAN}1.{END} Start Ollama server:")
    print(f"       {BOLD}ollama serve{END}")
    print(f"   {CYAN}2.{END} In another terminal, pull the model:")
    print(f"       {BOLD}ollama pull llama3.2:3b{END}")
    print(f"   {CYAN}3.{END} Verify connection:")
    print(f"       {BOLD}curl http://localhost:11434/api/tags{END}\n")
    
    try:
        # Test Ollama connection before running scenarios
        test_orchestrator = DemoOrchestrator()
        await test_orchestrator.initialize()
        await test_orchestrator.close()
        
        # Run scenarios
        await demo_scenario_1()
        await demo_scenario_2()
        await demo_scenario_3()
        await demo_scenario_4()
        
        print(f"\n{BOLD}{HEADER}")
        print("╔" + "═"*68 + "╗")
        print("║" + " "*68 + "║")
        print("║  ✅ ALL SCENARIOS COMPLETED SUCCESSFULLY".center(68) + "║")
        print("║  💡 All calls made to REAL local Ollama".center(68) + "║")
        print("║" + " "*68 + "║")
        print("╚" + "═"*68 + "╝")
        print(f"{END}\n")
        
        print(f"{BOLD}{GREEN}📊 Demo Summary:{END}")
        print(f"   {GREEN}✓{END} Scenario 1: Simple query (no rewriting)")
        print(f"   {GREEN}✓{END} Scenario 2: Mode switch (import ↔ export)")
        print(f"   {GREEN}✓{END} Scenario 3: Product tracking (electronics)")
        print(f"   {GREEN}✓{END} Scenario 4: Long conversation (5 turns)")
        print()
        
    except Exception as e:
        print(f"\n{RED}❌ Demo failed: {e}{END}")
        print(f"\n{BOLD}{YELLOW}Troubleshooting:{END}")
        print(f"   {RED}1.{END} Is Ollama running?")
        print(f"       → Run in a separate terminal: {CYAN}ollama serve{END}")
        print(f"   {RED}2.{END} Is llama3.2:3b installed?")
        print(f"       → Run: {CYAN}ollama pull llama3.2:3b{END}")
        print(f"   {RED}3.{END} Is Ollama accessible?")
        print(f"       → Test: {CYAN}curl http://localhost:11434/api/tags{END}")
        print(f"\n   If problem persists, check:")
        print(f"       - Ollama hostname/port (default: localhost:11434)")
        print(f"       - Firewall/network settings")
        print(f"       - Available disk space for model (~7GB for llama3.2:3b)")
        print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}⚠️  Demo interrupted by user{END}\n")
    except Exception as e:
        print(f"\n{RED}❌ Fatal error: {e}{END}\n")