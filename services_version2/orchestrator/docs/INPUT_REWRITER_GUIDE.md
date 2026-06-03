# Input Rewriting Layer - Implementation Guide

**Date**: April 10, 2026  
**Status**: ✅ Implemented  
**Version**: v2.1

---

## Overview

The **Input Rewriting Layer** maintains conversation context across multi-turn sessions and dynamically rewrites user input to be clearer, more contextual, and intent-aware.

### What It Does

```
User Input (ambiguous)
    ↓
Input Rewriter (with session context)
    ↓
Rewritten Input (clear + contextual)
    ↓
Intent Detection
    ↓
Service Routing
```

### Example Flow

**Turn 1:**

- **User**: "How much do I have to pay for importing rice?"
- **Session Database**: Creates session, stores topic=agriculture, mode=import
- **Rewriter**: No context yet → input as-is
- **Intent**: CALCULATION
- **Answer**: "Duty on rice is 5%..."

**Turn 2:**

- **User**: "How about export?"
- **Session Context**: Previous mode=import, product=rice
- **Rewriter**: "How much do I have to pay for exporting rice?" ← **Expanded!**
- **Intent**: CALCULATION
- **Answer**: "Export tax on rice is 2%..."

The rewriter detected the import→export switch and expanded the ambiguous input!

---

## Architecture

### Components

#### 1. **InputRewriter** (`core/input_rewriter.py`)

- Uses local **LLM (llama3.2:3b)** via Ollama
- Rewrites input based on session context
- Detects intent/topic changes
- Fills in missing information

**Key Methods:**

```python
# Main entry point
rewritten, metadata = await rewriter.rewrite_input(
    user_input="how about export?",
    context=session_context
)
```

#### 2. **SessionContext** (`core/input_rewriter.py`)

- Tracks conversation state per user session
- Maintains topic, product category, currency, import/export mode
- Keeps conversation history (last N turns)
- Automatically expires after 1 hour

**Key Fields:**

```python
session_context = SessionContext(
    session_id="user_123",
    current_topic=Topic.IMPORT,
    product_category="rice",
    currency="USD",
    import_export_mode="import"
)
```

#### 3. **SessionManager** (`core/input_rewriter.py`)

- Manages all active sessions
- Creates/retrieves/updates sessions
- Handles expiration and cleanup

**Key Methods:**

```python
# Get or create session
session = manager.get_or_create_session("user_123")

# Update context
manager.update_session_context(
    "user_123",
    product_category="coffee",
    import_export_mode="export"
)
```

### Integration Points

#### In Coordinator (`core/coordinator.py`)

The rewriter is now integrated into the main query processing flow:

```python
async def process_query(self, question: str, session_id: Optional[str] = None):
    # STEP 1: Rewrite input with session context
    if self.use_input_rewriter and session_id:
        session_context = self.session_manager.get_or_create_session(session_id)
        rewritten_question, metadata = await self.input_rewriter.rewrite_input(
            question, context=session_context
        )

    # STEP 2: Detect intent (using rewritten input)
    context.intent = self.workflow_executor.detect_intent(question)

    # STEP 3: Route and process
    await self._route_query(context)

    # STEP 4: Update session with results
    context.session_context.add_turn(user_input, bot_response)
```

---

## Setup & Configuration

### 1. Ensure Ollama is Running

```bash
# Start Ollama (if not already running)
ollama serve

# Verify llama3.2:3b is available
ollama list
# Output should show: llama3.2:3b    3.1 GB

# If not available, pull it:
ollama pull llama3.2:3b
```

### 2. Enable in Coordinator

When initializing the coordinator, pass rewriter settings:

```python
from core.coordinator import ServiceCoordinator

coordinator = ServiceCoordinator(
    retrieval_client=retrieval_client,
    calculator_client=calculator_client,
    trade_data_client=trade_data_client,
    use_input_rewriter=True,  # Enable rewriter
    ollama_host="http://localhost:11434",
    ollama_model="llama3.2:3b"
)
```

### 3. Pass Session ID in API Requests

When making API requests, include `session_id` to enable context rewriting:

```json
{
  "question": "how about export?",
  "session_id": "user_123_conversation_456"
}
```

---

## Usage Examples

### Example 1: Simple Multi-Turn Conversation

```python
import asyncio
from core.coordinator import ServiceCoordinator
from core.input_rewriter import get_session_manager

async def main():
    # Initialize
    coordinator = ServiceCoordinator(use_input_rewriter=True)
    session_id = "demo_user_001"

    # Turn 1: Initial question
    result1 = await coordinator.process_query(
        "How much import duty on rice?",
        session_id=session_id
    )
    print("Turn 1 Answer:", result1['answer'])

    # Turn 2: Ambiguous follow-up (rewriter will expand it)
    result2 = await coordinator.process_query(
        "What about export?",  # ← Will be rewritten to consider rice + export
        session_id=session_id
    )
    print("Turn 2 Answer:", result2['answer'])
    # Rewriter detected: mode switch from import → export
    # The actual question processed: "How much is the export duty on rice?"
```

### Example 2: Manual Session Management

```python
from core.input_rewriter import (
    SessionManager,
    InputRewriter,
    Topic
)

async def main():
    # Create instances
    session_mgr = SessionManager()
    rewriter = InputRewriter()

    # Get session
    session = session_mgr.get_or_create_session("user_456")

    # Update context
    session_mgr.update_session_context(
        "user_456",
        current_topic=Topic.TRADE,
        product_category="electronics",
        import_export_mode="import",
        currency="EUR"
    )

    # Rewrite input
    rewritten, metadata = await rewriter.rewrite_input(
        "What's the tax on that?",  # Ambiguous
        context=session
    )
    # Output: "What's the import tax on electronics?"

    print(f"Original: What's the tax on that?")
    print(f"Rewritten: {rewritten}")
    print(f"Confidence: {metadata['confidence']}")

    await rewriter.close()
```

### Example 3: Detect Intent Changes

```python
async def main():
    session_mgr = SessionManager()
    rewriter = InputRewriter()

    # Setup initial context (import rice)
    session = session_mgr.get_or_create_session("user_789")
    session.import_export_mode = "import"
    session.product_category = "rice"

    # User says "export"
    rewritten, metadata = await rewriter.rewrite_input(
        "export rice",
        context=session
    )

    print(f"Intent changed: {metadata['intent_changed']}")
    print(f"Topic switch: {metadata['topic_switch']}")
    print(f"Change reason: {metadata['reason']}")
    print(f"New mode: {metadata['new_mode']}")

    # Output:
    # Intent changed: True
    # Topic switch: True
    # Change reason: mode_switch_to_export
    # New mode: export

    await rewriter.close()
```

---

## Supported Topics & Modes

### Topics (`Topic` enum)

```python
class Topic(str, Enum):
    IMPORT = "import"
    EXPORT = "export"
    TRADE = "trade"
    HS_CODE = "hs_code"
    DUTY_TAX = "duty_tax"
    POLICY = "policy"
    DEFINITION = "definition"
    UNKNOWN = "unknown"
```

### Import/Export Modes

- **"import"**: Importing goods into the country
- **"export"**: Exporting goods out of the country
- **None**: Not yet determined

### Detected Intent Changes

The rewriter detects and handles:

1. **Mode switches** (import ↔ export)
   - Keywords: "import", "export", "shipping", "receiving"
   - Confidence: 0.9

2. **Ambiguous follow-ups** (e.g., "what about X?")
   - Keywords: "what", "about", "other", "else"
   - Confidence: 0.7

3. **Product changes**
   - Fills in from previous product if mentioned in context

---

## API Integration

### Request Format

```json
POST /query
{
  "question": "how about export?",
  "session_id": "user_123_conversation_456"
}
```

### Response Format

```json
{
  "request_id": "abc-123",
  "question": "how about export?",
  "answer": "The export duty on rice is 2%...",
  "intent": "calculation",
  "status": "success",
  "metadata": {
    "rewrite_reason": "mode_switch_to_export",
    "rewritten_input": "How much is the export duty on rice?",
    "session_id": "user_123_conversation_456"
  }
}
```

### Session ID Guidelines

1. **Unique per user**: One session_id per user/conversation
2. **Format**: `user_ID_conversation_ID` or similar
3. **Optional**: If omitted, uses session-less mode (no context)
4. **Persistent**: Use same session_id across multiple turns

---

## Performance Considerations

### Latency Impact

- **First turn (no context)**: ~50 ms (skip rewriter)
- **Subsequent turns**: ~200-400 ms (LLM rewrite)
- **Total latency**: Added 150-350 ms for rewriting

### Memory Usage

- Per session: ~10-50 KB (depends on conversation length)
- Max sessions: 1000 (default)
- Memory cap: ~50 MB for all sessions

### Optimization Tips

1. **Disable for first turns**: Check `is_first_turn` in metadata
2. **Cache rewritten inputs**: Store frequently rewritten patterns
3. **Tune LLM temperature**: Lower = faster, more consistent
4. **Batch rewritten queries**: Process multiple rewrites together

---

## Testing

### Run Unit Tests

```bash
cd services_version2/orchestrator_version2

# Run all rewriter tests
pytest tests/test_input_rewriter.py -v

# Run specific test
pytest tests/test_input_rewriter.py::TestInputRewriter::test_import_to_export_switch -v
```

### Test Coverage

| Component        | Coverage            |
| ---------------- | ------------------- |
| InputRewriter    | ✅ Rewriting logic  |
| SessionManager   | ✅ Session CRUD     |
| SessionContext   | ✅ Context updates  |
| Intent detection | ✅ Mode switches    |
| Topic management | ✅ Context tracking |

### Manual Testing

```python
# Start Python REPL
python

# Test rewriter directly
from core.input_rewriter import InputRewriter, SessionManager
import asyncio

async def test():
    rewriter = InputRewriter()
    mgr = SessionManager()

    session = mgr.get_or_create_session("test_user")
    session.product_category = "rice"
    session.import_export_mode = "import"

    # Test rewriting
    rewritten, metadata = await rewriter.rewrite_input(
        "how about export?",
        context=session
    )

    print(f"Rewritten: {rewritten}")
    print(f"Intent changed: {metadata['intent_changed']}")

    await rewriter.close()

asyncio.run(test())
```

---

## Troubleshooting

### Issue: "Connection refused" to Ollama

**Check:**

```bash
# Verify Ollama is running
curl http://localhost:11434/api/tags

# If not running, start it:
ollama serve
```

**Fix:** Ensure Ollama is running before coordinator starts.

### Issue: Model not found (llama3.2:3b)

**Check:**

```bash
ollama list
```

**Fix:**

```bash
ollama pull llama3.2:3b
```

### Issue: Input rewriting very slow (>1 second)

**Check:**

- Is llama3.2:3b the active model? (Check Ollama logs)
- What's your CPU/GPU utilization?
- Try reducing `max_turns` in SessionContext

**Fix:**

```python
# Disable rewriter for production if too slow
coordinator = ServiceCoordinator(
    use_input_rewriter=False  # Fallback to session-less mode
)
```

### Issue: Session context not persisting

**Check:**

- Is `session_id` being passed correctly?
- Is the session expired? (TTL: 1 hour)
- Are you using same `session_id` for multiple turns?

**Fix:**

```python
# Ensure session_id is passed consistently
result = await coordinator.process_query(
    "your question",
    session_id="same_session_id_every_turn"  # ← IMPORTANT
)
```

---

## Advanced Configuration

### Custom Session TTL

```python
session = SessionManager().get_or_create_session("user_123")
session.ttl_seconds = 7200  # 2 hours instead of 1 hour
```

### Custom LLM Model

```python
coordinator = ServiceCoordinator(
    use_input_rewriter=True,
    ollama_host="http://localhost:11434",
    ollama_model="mistral"  # Use different model
)
```

### Custom Topic Detection

Extend `Topic` enum:

```python
class Topic(str, Enum):
    IMPORT = "import"
    EXPORT = "export"
    # Add more topics as needed
```

---

## Monitoring & Observability

### Logging

The rewriter logs all important events:

```log
✓ Input Rewriter initialized
  LLM Host: http://localhost:11434
  Model: llama3.2:3b
[SessionManager] Created new session: user_123
[Rewriter] Input: how about export?
[Rewriter] Intent change detected: mode_switch_to_export
[Rewriter] Rewritten: 'how about export?' → 'How much do I have to pay for exporting rice?'
[SessionManager] Session updated: last_intent = calculation
```

### Metrics to Track

1. **Rewrite latency**: Avg/P95/P99 time for rewriting
2. **Intent change frequency**: % of queries with detected changes
3. **Session hit rate**: % of queries using existing sessions
4. **Memory usage**: Current active sessions
5. **Error rate**: % of failed rewrites

---

## Future Enhancements

### Planned Improvements

1. **Multi-language support**: Khmer, French, Chinese
2. **Entity extraction**: Automatically identify products, quantities
3. **Caching**: Store common rewrites to speed up
4. **Analytics**: Track which topics/modes most common
5. **Fine-tuning**: Train custom model for domain-specific rewrites

### Scalability

- **Distributed sessions**: Redis-backed session store
- **LLM clustering**: Multiple Ollama instances
- **Caching layer**: Redis for rewritten inputs

---

## API Reference

### `InputRewriter.rewrite_input()`

```python
async def rewrite_input(
    user_input: str,
    context: Optional[SessionContext] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Rewrite user input based on session context.

    Args:
        user_input: Raw user input
        context: Optional session context

    Returns:
        (rewritten_input, metadata) where metadata includes:
        - rewrite_reason: str (no_context, context_enrichment, mode_switch_to_import, etc.)
        - confidence: float (0.0-1.0)
        - is_first_turn: bool
        - intent_changed: bool
        - topic_switch: bool
    """
```

### `SessionManager.get_or_create_session()`

```python
def get_or_create_session(self, session_id: str) -> SessionContext:
    """Get existing session or create new one."""
```

### `SessionManager.update_session_context()`

```python
def update_session_context(
    self,
    session_id: str,
    **kwargs  # current_topic, product_category, currency, etc.
):
    """Update session context fields."""
```

---

## Questions?

For additional help:

1. Check test files: `tests/test_input_rewriter.py`
2. Review coordinator integration: `core/coordinator.py`
3. Check API usage: `api/endpoints.py`

---

**Last Updated**: April 10, 2026  
**Maintained By**: GDCE Chatbot Team
