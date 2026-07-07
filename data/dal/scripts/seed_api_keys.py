"""
Seed API keys for admin and developer access.

This script is separate from seed_metadata.py and only creates API key rows.
It is intended for local development and can be run independently.

Run: python -m scripts.seed_api_keys
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import delete

from app.core.security import hash_api_key
from app.db.metadata_session import get_metadata_session_factory
from app.db.models import ApiKey

ADMIN_KEY_PLAIN = "dal-admin-key-abc123xyz789"
DEVELOPER_KEY_PLAIN = "dal-dev-key-def456uvw012"

# ADMIN_KEY_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
# DEVELOPER_KEY_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
ADMIN_KEY_ID = uuid.uuid4()
DEVELOPER_KEY_ID = uuid.uuid4()


async def seed() -> None:
    """Insert admin and developer API keys into the metadata DB."""
    factory = get_metadata_session_factory()
    async with factory() as session:
        # Remove any existing rows for these client IDs so the script is repeatable.
        await session.execute(
            delete(ApiKey).where(
                ApiKey.client_id.in_([
                    "admin_client",
                    "developer_client",
                ])
            )
        )

        admin_key = ApiKey(
            key_id=ADMIN_KEY_ID,
            client_id="admin_client",
            hashed_key=hash_api_key(ADMIN_KEY_PLAIN),
            status="active",
            tier="admin",
            rate_limit_per_minute=120,
        )
        developer_key = ApiKey(
            key_id=DEVELOPER_KEY_ID,
            client_id="developer_client",
            hashed_key=hash_api_key(DEVELOPER_KEY_PLAIN),
            status="active",
            tier="developer",
            rate_limit_per_minute=60,
        )

        session.add(admin_key)
        session.add(developer_key)
        await session.commit()

    print("=" * 60)
    print("Admin/developer API keys seeded successfully!")
    print("=" * 60)
    print(f"Admin API key     (for dev only): {ADMIN_KEY_PLAIN}")
    print(f"Developer API key (for dev only): {DEVELOPER_KEY_PLAIN}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed())
