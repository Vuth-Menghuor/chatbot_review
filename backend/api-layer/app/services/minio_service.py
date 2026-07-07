import io
import logging
from functools import lru_cache

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache
def _get_client() -> Minio:
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_bucket() -> None:
    client = _get_client()
    bucket = settings.minio_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Created MinIO bucket: %s", bucket)


def upload_file(object_key: str, data: bytes, content_type: str) -> None:
    ensure_bucket()
    client = _get_client()
    client.put_object(
        settings.minio_bucket,
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def delete_file(object_key: str) -> None:
    client = _get_client()
    try:
        client.remove_object(settings.minio_bucket, object_key)
    except S3Error as exc:
        logger.warning("Failed to delete MinIO object %s: %s", object_key, exc)


def build_public_url(object_key: str) -> str | None:
    scheme = "https" if settings.minio_secure else "http"
    return f"{scheme}://{settings.minio_endpoint}/{settings.minio_bucket}/{object_key}"


def generate_presigned_url(object_key: str, expires_seconds: int = 3600) -> str:
    from datetime import timedelta

    ensure_bucket()
    client = _get_client()
    return client.presigned_get_object(
        settings.minio_bucket,
        object_key,
        expires=timedelta(seconds=expires_seconds),
    )
