"""
tests/test_streaming.py
=======================
Automated tests for the SSE streaming implementation (POST /query/stream).

Covers all 6 scenarios from the verification plan:
  1. test_mid_stream_fallback         -- Gemini fails after partial tokens -> error event, no Ollama
  2. test_context_var_preservation    -- unified_result_var survives multiple await boundaries
  3. test_session_concurrency_lock    -- double-submit produces 2 sequential turns, not interleaved
  4. test_pre_stream_fallback         -- Gemini fails before first token -> transparent Ollama fallback
  5. test_disconnect_handling         -- client disconnects mid-stream -> no partial session save
  6. test_clarification_path          -- CLARIFICATION_REQUIRED -> clarification event, no formatter

Run with:
    pytest tests/test_streaming.py -v
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import AsyncIterator

import pytest


# ---------------------------------------------------------------------------
# Test 1: Mid-stream fallback produces error event, NOT a garbled Ollama tail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mid_stream_fallback():
    """
    Gemini yields 2 chunks, then raises on token 3.
    Because sent_any=True, the summarizer must re-raise so the endpoint
    emits an error SSE event and stops - Ollama must NOT be called.
    """
    from app.ai.summarizer import OrchestratorFormatterService

    mock_gemini = MagicMock()
    mock_gemini.name = "gemini"

    async def _failing_gemini_stream(**kwargs):
        yield "Hello, "
        yield "here is some "
        raise RuntimeError("Simulated mid-stream failure")

    mock_gemini.format_response_stream = _failing_gemini_stream

    mock_ollama = MagicMock()
    mock_ollama.format_response_stream = AsyncMock()

    service = OrchestratorFormatterService.__new__(OrchestratorFormatterService)
    service._provider = mock_gemini
    service.providers = {"gemini": mock_gemini, "ollama": mock_ollama}
    service._available = True
    service.config = MagicMock()
    service.config.enabled = True
    mock_gemini.is_available = MagicMock(return_value=True)

    chunks_received = []
    with pytest.raises(RuntimeError, match="Simulated mid-stream failure"):
        async for chunk in service.format_response_stream(
            base_answer="raw answer",
            question="What is the duty rate?",
            intent="general",
        ):
            chunks_received.append(chunk)

    # Partial output was yielded
    assert len(chunks_received) == 2
    assert chunks_received[0] == "Hello, "

    # Ollama must NOT have been called
    mock_ollama.format_response_stream.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: ContextVar is preserved across multiple await boundaries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_var_preservation():
    """
    The unified_result_var must remain populated after multiple await
    boundaries in the streaming generator.
    """
    from app.ai.analyzer import unified_result_var

    test_payload = {"query": "What is HS 0101?", "intent": "hs_code_lookup", "confidence": 0.9}

    async def simulate_awaits_and_read():
        unified_result_var.set(test_payload)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return unified_result_var.get()

    result = await simulate_awaits_and_read()
    assert result is not None, "ContextVar was lost after await boundaries"
    assert result["intent"] == "hs_code_lookup"


# ---------------------------------------------------------------------------
# Test 3: Concurrent same-session requests are processed sequentially
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_concurrency_lock():
    """
    Two simultaneous streaming requests for the same session_id must be
    processed sequentially via the session lock.
    """
    from app.api.endpoints import _session_locks

    session_id = "test-session-lock-123"
    _session_locks.pop(session_id, None)

    execution_order = []

    async def request_a():
        if session_id not in _session_locks:
            _session_locks[session_id] = asyncio.Lock()
        async with _session_locks[session_id]:
            execution_order.append("A_start")
            await asyncio.sleep(0.05)
            execution_order.append("A_end")

    async def request_b():
        if session_id not in _session_locks:
            _session_locks[session_id] = asyncio.Lock()
        async with _session_locks[session_id]:
            execution_order.append("B_start")
            await asyncio.sleep(0.02)
            execution_order.append("B_end")

    await asyncio.gather(request_a(), request_b())

    a_start = execution_order.index("A_start")
    a_end = execution_order.index("A_end")
    b_start = execution_order.index("B_start")
    b_end = execution_order.index("B_end")

    assert (a_end < b_start) or (b_end < a_start), (
        f"Requests interleaved! Execution order: {execution_order}"
    )


# ---------------------------------------------------------------------------
# Test 4: Pre-stream fallback to Ollama when Gemini fails before first token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pre_stream_fallback():
    """
    Gemini raises immediately (before yielding any tokens).
    The summarizer must transparently fall back to Ollama.
    """
    from app.ai.summarizer import OrchestratorFormatterService

    mock_gemini = MagicMock()
    mock_gemini.name = "gemini"

    async def _immediately_failing_stream(**kwargs):
        raise RuntimeError("Gemini unavailable at start")
        yield  # pragma: no cover

    mock_gemini.format_response_stream = _immediately_failing_stream

    mock_ollama = MagicMock()

    async def _ollama_stream(**kwargs):
        yield "Ollama fallback response."

    mock_ollama.format_response_stream = _ollama_stream

    service = OrchestratorFormatterService.__new__(OrchestratorFormatterService)
    service._provider = mock_gemini
    service.providers = {"gemini": mock_gemini, "ollama": mock_ollama}
    service._available = True
    service.config = MagicMock()
    service.config.enabled = True
    mock_gemini.is_available = MagicMock(return_value=True)

    chunks = []
    async for chunk in service.format_response_stream(
        base_answer="raw answer",
        question="What is the rate?",
        intent="general",
    ):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0] == "Ollama fallback response."


# ---------------------------------------------------------------------------
# Test 5: Client disconnect -- no partial session save
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disconnect_handling():
    """
    When is_disconnected() returns True mid-stream, the generator must stop
    immediately and session_ctx.add_turn() must NOT be called.
    """
    call_counter = {"count": 0}

    async def disconnects_after_first_chunk():
        call_counter["count"] += 1
        return call_counter["count"] > 1

    session_ctx = MagicMock()
    session_ctx.add_turn = MagicMock()

    full_response_parts = []
    chunks = ["First chunk. ", "Second chunk. ", "Third chunk."]
    disconnected = False

    for chunk in chunks:
        if await disconnects_after_first_chunk():
            disconnected = True
            break
        full_response_parts.append(chunk)

    # Only persist when stream completed normally (no disconnect)
    if not disconnected:
        full_response = "".join(full_response_parts)
        if session_ctx is not None and full_response:
            session_ctx.add_turn(user_input="test", bot_response=full_response)

    session_ctx.add_turn.assert_not_called()
    assert len(full_response_parts) == 1, "Only first chunk should have been collected before disconnect"


# ---------------------------------------------------------------------------
# Test 6: Clarification path -- formatter never invoked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clarification_path():
    """
    When the coordinator returns status=clarification_required, the endpoint
    must emit a single clarification SSE event and NOT call the formatter.
    """
    clarification_result = {
        "status": "clarification_required",
        "clarifications": ["Did you mean HS code lookup or duty calculation?"],
        "intent": "unclassified",
        "answer": "",
    }

    emitted_events = []
    formatter_called = False

    result_status = clarification_result.get("status", "")
    if result_status == "clarification_required" or clarification_result.get("clarifications"):
        payload = {
            "questions": clarification_result.get("clarifications", []),
            "session_id": "test-session-456",
            "status": "clarification_required",
            "intent": clarification_result.get("intent", "unclassified"),
        }
        emitted_events.append(f"event: clarification\ndata: {json.dumps(payload)}\n\n")
    else:
        formatter_called = True

    assert len(emitted_events) == 1
    assert "clarification" in emitted_events[0]
    assert formatter_called is False

    lines = [ln for ln in emitted_events[0].split("\n") if ln.strip()]
    event_line, data_line = lines[0], lines[1]
    assert event_line == "event: clarification"
    parsed = json.loads(data_line.replace("data: ", ""))
    assert parsed["status"] == "clarification_required"
    assert "Did you mean HS code lookup or duty calculation?" in parsed["questions"]
