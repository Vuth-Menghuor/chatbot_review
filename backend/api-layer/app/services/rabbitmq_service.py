import json
import logging
from typing import Any

import aio_pika

from app.core.config import settings

logger = logging.getLogger(__name__)


async def _connect() -> aio_pika.RobustConnection:
    url = (
        f"amqp://{settings.rabbitmq_user}:{settings.rabbitmq_password}"
        f"@{settings.rabbitmq_host}:{settings.rabbitmq_port}/"
    )
    return await aio_pika.connect_robust(url)


async def publish_image_event(event: str, payload: dict[str, Any]) -> None:
    message_body = {"event": event, **payload}
    connection = await _connect()
    try:
        channel = await connection.channel()
        await channel.declare_queue(settings.rabbitmq_image_queue, durable=True)
        message = aio_pika.Message(
            body=json.dumps(message_body).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        await channel.default_exchange.publish(message, routing_key=settings.rabbitmq_image_queue)
        logger.info("Published RabbitMQ event %s for file_id=%s", event, payload.get("file_id"))
    finally:
        await connection.close()
