import pytest
from pydantic import ValidationError

from app.schemas.common import ChatRequest, UserCreate


def test_chat_message_cannot_be_blank():
    with pytest.raises(ValidationError):
        ChatRequest(message="   ")


def test_password_requires_eight_characters():
    with pytest.raises(ValidationError):
        UserCreate(full_name="Test", email="test@example.com", password="short")
