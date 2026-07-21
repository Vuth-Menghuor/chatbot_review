import asyncio
from uuid import uuid4

from app.services.ownership import create_or_get_chat


class FakeChatDb:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = None
        self.flushed = False

    async def get(self, _model, _item_id):
        return self.existing

    def add(self, item):
        self.added = item

    async def flush(self):
        self.flushed = True


def test_client_supplied_chat_id_is_created_on_first_use():
    chat_id = uuid4()
    user_id = uuid4()
    db = FakeChatDb()

    chat = asyncio.run(
        create_or_get_chat(
            db,
            user_id=user_id,
            chat_id=chat_id,
            project_id=None,
            message="What documents do I need to import goods into Cambodia?",
        )
    )

    assert chat.id == chat_id
    assert chat.user_id == user_id
    assert db.added is chat
    assert db.flushed is True
