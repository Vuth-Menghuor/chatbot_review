import io
import logging
import os
from functools import lru_cache

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


@lru_cache
def _client() -> Minio:
    return Minio(
        os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
    )


def bucket_name() -> str:
    return os.environ.get("MINIO_BUCKET", "chatbot-files")


def download_file(object_key: str) -> bytes:
    client = _client()
    response = client.get_object(bucket_name(), object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def upload_file(object_key: str, data: bytes, content_type: str) -> None:
    client = _client()
    client.put_object(
        bucket_name(),
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def delete_file(object_key: str) -> None:
    client = _client()
    try:
        client.remove_object(bucket_name(), object_key)
    except S3Error as exc:
        logger.warning("Failed to delete object %s: %s", object_key, exc)


def thumbnail_object_key(object_key: str) -> str:
    path, _, filename = object_key.rpartition("/")
    stem, _, ext = filename.rpartition(".")
    thumb_name = f"{stem}_thumb.{ext or 'jpg'}"
    if path:
        return f"{path}/thumbnails/{thumb_name}"
    return f"thumbnails/{thumb_name}"
