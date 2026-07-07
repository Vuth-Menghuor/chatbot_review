import io
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import UploadFile
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models import FileRecord, User
from app.services import file_service


def _make_png_bytes(size: int = 128) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * max(size - 8, 0)


def _make_png_upload(name: str = "photo.png", size: int = 128) -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(_make_png_bytes(size)), headers={"content-type": "image/png"})


def _make_user(role: str = "user") -> User:
    return User(
        id=uuid4(),
        full_name="Test User",
        email="test@example.com",
        hashed_password="hashed",
        role=role,
        is_active=True,
    )


@pytest.fixture
def auth_user():
    user = _make_user()
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _flush():
        for call in db.add.call_args_list:
            obj = call[0][0]
            if hasattr(obj, "id") and obj.id is None:
                obj.id = uuid4()

    db.flush = AsyncMock(side_effect=_flush)
    db.refresh = AsyncMock()

    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_upload_valid_image(client, auth_user, mock_db):
    with patch("app.services.file_service.minio_service.upload_file") as upload_mock, patch(
        "app.api.v1.endpoints.files.rabbitmq_service.publish_image_event", new_callable=AsyncMock
    ) as publish_mock, patch("app.services.file_service.minio_service.build_public_url", return_value="http://minio/file"):
        response = await client.post(
            "/api/v1/files/upload-image",
            files={"file": ("photo.png", io.BytesIO(_make_png_bytes()), "image/png")},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["bucket"] == settings.minio_bucket
    assert body["status"] == "pending"
    assert body["object_key"].startswith(f"users/{auth_user.id}/")
    upload_mock.assert_called_once()
    publish_mock.assert_awaited_once()
    assert publish_mock.await_args.args[0] == "image.uploaded"
    assert mock_db.add.called
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reject_invalid_file_type(client, auth_user, mock_db):
    response = await client.post(
        "/api/v1/files/upload-image",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_reject_over_size_file(client, auth_user, mock_db):
    oversized = _make_png_bytes(settings.max_image_size_bytes + 1)
    response = await client.post(
        "/api/v1/files/upload-image",
        files={"file": ("big.png", io.BytesIO(oversized), "image/png")},
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_reject_unauthenticated_upload(client):
    response = await client.post(
        "/api/v1/files/upload-image",
        files={"file": ("photo.png", io.BytesIO(_make_png_bytes()), "image/png")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_reject_update_for_other_users_file(client, auth_user, mock_db):
    other_user = _make_user()
    file_record = FileRecord(
        id=uuid4(),
        user_id=other_user.id,
        bucket_name=settings.minio_bucket,
        object_key=f"users/{other_user.id}/{uuid4()}.png",
        original_name="other.png",
        content_type="image/png",
        size_bytes=100,
        file_type="image",
        status="pending",
    )
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: file_record))

    response = await client.put(
        f"/api/v1/files/{file_record.id}/update-image",
        files={"file": ("photo.png", io.BytesIO(_make_png_bytes()), "image/png")},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_metadata_saved_on_upload(client, auth_user, mock_db):
    with patch("app.services.file_service.minio_service.upload_file"), patch(
        "app.api.v1.endpoints.files.rabbitmq_service.publish_image_event", new_callable=AsyncMock
    ), patch("app.services.file_service.minio_service.build_public_url", return_value="http://minio/file"):
        response = await client.post(
            "/api/v1/files/upload-image",
            files={"file": ("photo.png", io.BytesIO(_make_png_bytes()), "image/png")},
        )

    assert response.status_code == 201
    assert "file_id" in response.json()
    assert response.json()["url"] == "http://minio/file"


def test_validate_image_file_accepts_png():
    upload = _make_png_upload()
    content_type = file_service.validate_image_file(upload.content_type, 128, upload.filename)
    assert content_type == "image/png"


@pytest.mark.asyncio
async def test_rabbitmq_publish_called_on_upload(auth_user):
    db = AsyncMock()
    db.add = MagicMock()

    async def _flush():
        for call in db.add.call_args_list:
            obj = call[0][0]
            if hasattr(obj, "id") and obj.id is None:
                obj.id = uuid4()

    db.flush = AsyncMock(side_effect=_flush)
    db.refresh = AsyncMock()

    upload = _make_png_upload()
    with patch("app.services.file_service.minio_service.upload_file"), patch(
        "app.services.file_service.minio_service.build_public_url", return_value="http://minio/file"
    ):
        result, pending = await file_service.upload_image(db, auth_user, upload)

    assert pending.event == "image.uploaded"
    assert pending.payload["job_id"]
    assert result.file_id
