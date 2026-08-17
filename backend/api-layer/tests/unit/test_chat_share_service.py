from __future__ import annotations

import asyncio
from uuid import uuid4

from app.services import chat_share_service
from app.services.chat_share_service import (
    normalize_snapshot_messages,
    snapshot_has_renderable_assistant_blocks,
)


class FakeChat:
    id = uuid4()
    title = "Calculate tax for HS 0102.29.11 CIF $800"


class FakeDb:
    def __init__(self) -> None:
        self.added = None

    def add(self, item):
        self.added = item


def structured_client_snapshot():
    return [
        {
            "id": "user-1",
            "role": "user",
            "content": "Calculate tax for HS 0102.29.11 CIF $800 from Thailand",
        },
        {
            "id": "assistant-1",
            "role": "assistant",
            "content": "Import Tax Calculation",
            "status": "completed",
            "responseStatus": "completed",
            "responseMode": "stream",
            "generationDurationMs": 6300,
            "coverage": "complete",
            "blocks": [
                {
                    "id": "summary-1",
                    "type": "summary",
                    "content": {
                        "title": "Import Tax Calculation",
                        "items": [{"label": "CIF Value", "value": "800.00 USD"}],
                    },
                },
                {
                    "id": "table-1",
                    "type": "table",
                    "content": {
                        "title": "Final Tax Breakdown",
                        "columns": [{"key": "type", "label": "Type"}],
                        "rows": [{"type": "VOP"}],
                    },
                },
            ],
            "sources": [{"title": "GDCE source", "id": "src-1"}],
            "normalizedResponse": {"api_version": "1.0", "status": "completed"},
        },
    ]


def test_normalize_snapshot_messages_preserves_renderer_fields():
    messages = normalize_snapshot_messages(structured_client_snapshot())
    assistant = messages[1]

    assert assistant["status"] == "completed"
    assert assistant["responseStatus"] == "completed"
    assert assistant["responseMode"] == "stream"
    assert assistant["generationDurationMs"] == 6300
    assert assistant["coverage"] == "complete"
    assert [block["type"] for block in assistant["blocks"]] == ["summary", "table"]
    assert assistant["sources"][0]["title"] == "GDCE source"
    assert assistant["normalizedResponse"]["api_version"] == "1.0"
    assert snapshot_has_renderable_assistant_blocks(messages) is True


def test_public_share_prefers_structured_client_snapshot_over_plain_orchestrator(monkeypatch):
    async def fake_get_share_by_chat(*_args, **_kwargs):
        return None

    async def fake_get_orchestrator_snapshot(_chat_id):
        return [
            {
                "id": "assistant-plain",
                "role": "assistant",
                "content": "FINAL TAX BREAKDOWN\n| Type | Tax base |",
            }
        ]

    async def fake_new_share_token(_db):
        return "share-token"

    monkeypatch.setattr(chat_share_service, "get_share_by_chat", fake_get_share_by_chat)
    monkeypatch.setattr(chat_share_service, "get_orchestrator_snapshot", fake_get_orchestrator_snapshot)
    monkeypatch.setattr(chat_share_service, "new_share_token", fake_new_share_token)
    monkeypatch.setattr(chat_share_service, "add_audit_log", lambda *_args, **_kwargs: None)

    share = asyncio.run(chat_share_service.create_or_update_share(
        FakeDb(),
        FakeChat(),
        uuid4(),
        "public",
        structured_client_snapshot(),
    ))

    assistant = share.message_snapshot[1]
    assert [block["type"] for block in assistant["blocks"]] == ["summary", "table"]
    assert "FINAL TAX BREAKDOWN" not in assistant["content"]
