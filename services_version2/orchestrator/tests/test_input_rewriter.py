
"""
Integration tests for Input Rewriting Layer
"""

# Add workspace root to sys.path for proper imports
import sys
import os
test_dir = os.path.dirname(os.path.abspath(__file__))
orchestrator_dir = os.path.dirname(test_dir)
services_v2_dir = os.path.dirname(orchestrator_dir)
workspace_root = os.path.dirname(services_v2_dir)
sys.path.insert(0, workspace_root)

import pytest
import asyncio
import logging
from services_version2.orchestrator.core.input_rewriter import (
    InputRewriter, SessionManager, SessionContext, Topic
)

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
class TestInputRewriter:
    """Test input rewriting functionality."""
    
    @pytest.fixture
    async def rewriter(self):
        """Create rewriter instance."""
        rewriter = InputRewriter(
            ollama_host="http://localhost:11434",
            model="llama3.2:3b"
        )
        yield rewriter
        await rewriter.close()
    
    @pytest.fixture
    def session_manager(self):
        """Create session manager instance."""
        return SessionManager()
    
    async def test_first_turn_no_rewrite(self, rewriter):
        """First turn should return input as-is."""
        user_input = "how much do I have to pay for importing rice?"
        rewritten, metadata = await rewriter.rewrite_input(user_input, context=None)
        
        assert rewritten == user_input
        assert metadata["is_first_turn"] is True
        assert metadata["confidence"] == 1.0
    
    @pytest.mark.asyncio
    async def test_import_to_export_switch(self, rewriter):
        """Test switching from import to export."""
        session_mgr = SessionManager()
        
        # Setup session with import context
        session = session_mgr.get_or_create_session("test_session_123")
        session.import_export_mode = "import"
        session.product_category = "rice"
        session.product_category_km = "ស្ rice?"
        session.add_turn(
            "how much to import rice?",
            "The duty for rice is..."
        )
        
        # User asks about export
        user_input = "how about export?"
        rewritten, metadata = await rewriter.rewrite_input(user_input, context=session)
        
        logger.debug(f"Rewritten: {rewritten}")
        logger.debug(f"Metadata: {metadata}")
        
        # Should expand to include export and rice
        assert "export" in rewritten.lower()
        assert metadata["intent_changed"] is True
    
    async def test_ambiguous_followup_expansion(self, rewriter):
        """Test expanding ambiguous followup with context."""
        session_mgr = SessionManager()
        
        # Setup session
        session = session_mgr.get_or_create_session("test_session_456")
        session.import_export_mode = "import"
        session.product_category = "electronics"
        session.currency = "USD"
        session.add_turn(
            "import electronics from China",
            "Your import tax would be $500..."
        )
        
        # Ambiguous input
        user_input = "what if value is higher?"
        rewritten, metadata = await rewriter.rewrite_input(user_input, context=session)
        
        logger.debug(f"Original: {user_input}")
        logger.debug(f"Rewritten: {rewritten}")
        
        # Should clarify it's still about importing electronics
        assert "import" in rewritten.lower() or "electronics" in rewritten.lower()

    async def test_hs_code_description_rewrite(self, rewriter):
        """HS code queries that ask what a code refers to should become description lookups."""
        user_input = "this hs code 0101.29.00 refer to what?"

        rewritten, metadata = await rewriter.rewrite_input(user_input, context=None)

        assert rewritten == "What is the product description of HS code 0101.29.00?"
        assert metadata["rewritten"] is True


class TestSessionManager:
    """Test session management."""
    
    def test_create_session(self):
        """Test session creation."""
        manager = SessionManager()
        
        session = manager.get_or_create_session("session_123")
        
        assert session.session_id == "session_123"
        assert session.current_topic == Topic.UNKNOWN
        assert session.import_export_mode is None
    
    def test_session_retrieval(self):
        """Test session retrieval."""
        manager = SessionManager()
        
        # Create session
        session1 = manager.get_or_create_session("session_456")
        session1.product_category = "rice"
        
        # Retrieve same session
        session2 = manager.get_or_create_session("session_456")
        
        assert session2.product_category == "rice"
        assert session1 is session2
    
    def test_update_session_context(self):
        """Test context update."""
        manager = SessionManager()
        
        session = manager.get_or_create_session("session_789")
        manager.update_session_context(
            "session_789",
            product_category="coffee",
            import_export_mode="export",
            currency="EUR"
        )
        
        assert session.product_category == "coffee"
        assert session.import_export_mode == "export"
        assert session.currency == "EUR"
    
    def test_session_expiration(self):
        """Test session TTL expiration."""
        manager = SessionManager()
        
        session = manager.get_or_create_session("session_expire")
        
        # Session should be valid initially
        assert not session.is_expired()
        
        # Simulate expiration by setting old creation time
        session.created_at = session.created_at - \
            __import__('datetime').timedelta(seconds=3700)  # 61+ minutes
        
        # Should be expired now
        assert session.is_expired()


class TestSessionContext:
    """Test session context."""
    
    def test_context_initialization(self):
        """Test context initialization."""
        ctx = SessionContext(session_id="ctx_123")
        
        assert ctx.session_id == "ctx_123"
        assert ctx.turns == []
        assert ctx.created_at is not None
    
    def test_add_turn(self):
        """Test adding conversation turns."""
        ctx = SessionContext(session_id="ctx_456")
        
        ctx.add_turn(
            "What is HS code?",
            "HS code is Harmonized System code..."
        )
        ctx.add_turn(
            "For rice?",
            "For rice, it's 1006..."
        )
        
        assert len(ctx.turns) == 2
        assert ctx.turns[0]["user"] == "What is HS code?"
        assert ctx.turns[1]["user"] == "For rice?"
    
    def test_turn_max_limit(self):
        """Test max turns limit."""
        ctx = SessionContext(session_id="ctx_789", max_turns=5)
        
        # Add 10 turns
        for i in range(10):
            ctx.add_turn(f"Question {i}", f"Answer {i}")
        
        # Should only keep last 5
        assert len(ctx.turns) == 5
        assert ctx.turns[0]["user"] == "Question 5"
        assert ctx.turns[-1]["user"] == "Question 9"
    
    def test_context_to_dict(self):
        """Test context serialization."""
        ctx = SessionContext(
            session_id="ctx_serialize",
            product_category="tea",
            import_export_mode="import"
        )
        
        data = ctx.to_dict()
        
        assert data["session_id"] == "ctx_serialize"
        assert data["product_category"] == "tea"
        assert data["import_export_mode"] == "import"


if __name__ == "__main__":
    # Run tests
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    logger = logging.getLogger(__name__)
    
    # Note: Make sure Ollama is running on localhost:11434
    pytest.main([__file__, "-v", "-s"])
