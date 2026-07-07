import json
import logging
import os
import sys
import time
from pathlib import Path

import pika

WORKER_ROOT = Path(__file__).resolve().parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from services import db_service, image_processor, minio_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("image-worker")


def _rabbit_url() -> str:
    user = os.environ.get("RABBITMQ_USER", "guest")
    password = os.environ.get("RABBITMQ_PASSWORD", "guest")
    host = os.environ.get("RABBITMQ_HOST", "rabbitmq")
    port = os.environ.get("RABBITMQ_PORT", "5672")
    return f"amqp://{user}:{password}@{host}:{port}/"


def _handle_upload_or_update(payload: dict) -> None:
    file_id = payload["file_id"]
    job_id = payload.get("job_id")
    object_key = payload["object_key"]
    content_type = payload.get("content_type", "image/jpeg")

    if not db_service.file_exists(file_id):
        raise RuntimeError(f"File record not found or deleted: {file_id}")

    image_data = minio_service.download_file(object_key)
    thumbnail_data, thumb_content_type = image_processor.process_image(image_data, content_type)
    thumb_key = minio_service.thumbnail_object_key(object_key)
    minio_service.upload_file(thumb_key, thumbnail_data, thumb_content_type)

    scheme = "https" if os.environ.get("MINIO_SECURE", "false").lower() == "true" else "http"
    endpoint = os.environ["MINIO_ENDPOINT"]
    bucket = minio_service.bucket_name()
    public_url = f"{scheme}://{endpoint}/{bucket}/{thumb_key}"
    db_service.mark_file_processed(file_id, public_url=public_url)

    if job_id:
        db_service.mark_job_completed(job_id)


def _handle_deleted(payload: dict) -> None:
    object_key = payload.get("object_key")
    old_object_key = payload.get("old_object_key")
    job_id = payload.get("job_id")

    keys = [key for key in [object_key, old_object_key] if key]
    for key in keys:
        minio_service.delete_file(key)
        minio_service.delete_file(minio_service.thumbnail_object_key(key))

    if job_id:
        db_service.mark_job_completed(job_id)


def _process_message(body: bytes) -> None:
    payload = json.loads(body.decode("utf-8"))
    event = payload.get("event")
    logger.info("Processing event=%s file_id=%s", event, payload.get("file_id"))

    if event in {"image.uploaded", "image.updated"}:
        _handle_upload_or_update(payload)
    elif event == "image.deleted":
        _handle_deleted(payload)
    else:
        raise RuntimeError(f"Unsupported event: {event}")


def _on_message(channel, method, _properties, body):
    job_id = None
    try:
        payload = json.loads(body.decode("utf-8"))
        job_id = payload.get("job_id")
        _process_message(body)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        logger.exception("Failed to process message: %s", exc)
        if job_id:
            db_service.mark_job_failed(job_id, str(exc))
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main() -> None:
    queue_name = os.environ.get("RABBITMQ_IMAGE_QUEUE", "image_jobs")
    retry_seconds = 5

    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(_rabbit_url()))
            channel = connection.channel()
            channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue_name, on_message_callback=_on_message, auto_ack=False)
            logger.info("Image worker listening on queue=%s", queue_name)
            channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Shutting down image worker")
            sys.exit(0)
        except Exception as exc:
            logger.exception("Worker connection error: %s", exc)
            time.sleep(retry_seconds)


if __name__ == "__main__":
    main()
