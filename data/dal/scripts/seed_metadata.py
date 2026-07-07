"""
Seed metadata database with sample data for local development.

Seeds:
- 1 dataset (trade_volume)
- 1 dataset version (1.0, default)
- 1 dataset mapping with the full trade_volume concept
- 2 API keys (public_client, private_client)
- 1 API key → dataset grant (private_client → trade_volume)
- 1 cache policy

Run: python -m scripts.seed_metadata
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_api_key
from app.db.metadata_session import get_metadata_session_factory
from app.db.models import (
    ApiKey,
    ApiKeyDataset,
    Base,
    CachePolicy,
    Dataset,
    DatasetMapping,
    DatasetVersion,
)

# --- Sample plaintext API keys (ONLY for local dev output) ---
PUBLIC_KEY_PLAIN = "dal-pub-key-abc123xyz789"
PRIVATE_KEY_PLAIN = "dal-priv-key-def456uvw012"

# Fixed UUIDs for reproducibility
DATASET_ID = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
PUBLIC_KEY_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
PRIVATE_KEY_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

TRADE_VOLUME_CONCEPT = {
    "dataset-code": "trade_volume",
    "version": "1.0",
    "frequency": {
        "code": "FREQ",
        "query": {
            "base": "FREQ",
            "case": {
                "a": "'A'",
                "m": "'M'",
                "q": "'Q'",
                "s": "'S'",
            },
        },
        "default": "A"
    },
    "period": {
        "code": "PERIOD",
        "query": {
            "base": "FREQ",
            "case": {
                "a": "td.ref_year::TEXT",
                "m": "td.ref_year || '-' || LPAD(td.ref_month::TEXT, 2, '0')",
                "q": "td.ref_year || '-Q' || CEIL(td.ref_month / 3.0)::TEXT",
                "s": "td.ref_year || '-S' || CEIL(td.ref_month / 6.0)::TEXT",
            },
        },
        "filters": {
            "start-period": {
                "pattern-test": {
                    "yyyy": r"\d{4}$",
                    "yyyy-mm": r"\d{4}-\d{2}$",
                    "yyyy-q1": r"\d{4}-[Qq]1$",
                    "yyyy-q2": r"\d{4}-[Qq]2$",
                    "yyyy-q3": r"\d{4}-[Qq]3$",
                    "yyyy-q4": r"\d{4}-[Qq]4$",
                    "yyyy-s1": r"\d{4}-[Ss]1$",
                    "yyyy-s2": r"\d{4}-[Ss]2$",
                },
                "query": {
                    "yyyy": "td.ref_year >= {VALUE}",
                    "yyyy-mm": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= replace(({VALUE})::text, '-', '')::integer",
                    "yyyy-q1": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= concat(({VALUE0})::text,'01')::integer",
                    "yyyy-q2": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= concat(({VALUE0})::text,'04')::integer",
                    "yyyy-q3": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= concat(({VALUE0})::text,'07')::integer",
                    "yyyy-q4": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= concat(({VALUE0})::text,'10')::integer",
                    "yyyy-s1": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= concat(({VALUE0})::text,'01')::integer",
                    "yyyy-s2": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= concat(({VALUE0})::text,'07')::integer",
                },
            },
            "end-period": {
                "pattern-test": {
                    "yyyy": r"\d{4}$",
                    "yyyy-mm": r"\d{4}-\d{2}$",
                    "yyyy-q1": r"\d{4}-[Qq]1$",
                    "yyyy-q2": r"\d{4}-[Qq]2$",
                    "yyyy-q3": r"\d{4}-[Qq]3$",
                    "yyyy-q4": r"\d{4}-[Qq]4$",
                    "yyyy-s1": r"\d{4}-[Ss]1$",
                    "yyyy-s2": r"\d{4}-[Ss]2$",
                },
                "query": {
                    "yyyy": "td.ref_year <= {VALUE}",
                    "yyyy-mm": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= replace(({VALUE})::text, '-', '')::integer",
                    "yyyy-q1": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= concat(({VALUE0})::text,'03')::integer",
                    "yyyy-q2": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= concat(({VALUE0})::text,'06')::integer",
                    "yyyy-q3": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= concat(({VALUE0})::text,'09')::integer",
                    "yyyy-q4": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= concat(({VALUE0})::text,'12')::integer",
                    "yyyy-s1": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= concat(({VALUE0})::text,'06')::integer",
                    "yyyy-s2": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= concat(({VALUE0})::text,'12')::integer",
                },
            },
        }
    },
    "dimensions": [
        {"code": "PARTNER_COUNTRY", "query": "c.name_en"},
        {"code": "MODE_OF_TRANSPORT", "query": "mot.name_en"},
        {"code": "FLOW", "query": "td.flow"},
    ],
    "measures": [
        {"code": "VALUE_USD", "query": "td.value_usd", "aggregate": "SUM"},
        {"code": "NETWEIGHT", "query": "td.net_weight", "aggregate": "SUM"},
        {
            "code": "QUANTITY",
            "query": "COALESCE(td.quantity, td.net_weight)",
            "aggregate": "SUM",
            "unit": {"code": "UNIT", "query": "COALESCE(td.supp_unit, 'KGM')"},
        },
    ],
    "source": {
        "connection-key": "operational_db",
        "schema": "public",
        "table": "trade_data as td",
        "join": [
            {
                "table": "countries as c",
                "type": "inner",
                "on": "td.partner_country = c.country_code",
            },
            {
                "table": "mode_of_transport as mot",
                "type": "inner",
                "on": "td.mode_of_transport = mot.mode_of_transport_code",
            },
        ],
    },
    "filters": {
        "partner_country": {
            "query": "c.country_code"
        }
    },
    "security": {"allow-raw-sql": False},
}


async def seed():
    """Insert sample metadata records."""
    factory = get_metadata_session_factory()
    async with factory() as session:
        # Clean existing data
        for table in [
            "audit_log",
            "cache_policy",
            "api_key_dataset",
            "api_key",
            "dataset_mapping",
            "dataset_version",
            "dataset",
        ]:
            await session.execute(text(f"DELETE FROM {table}"))

        # --- Dataset ---
        ds = Dataset(
            dataset_id=DATASET_ID,
            dataset_code="trade_volume",
            name="Trade Volume",
            description="International trade volume data with partner countries and transport modes",
            is_public=True,
            status="active",
        )
        session.add(ds)

        # --- Dataset Version ---
        dv = DatasetVersion(
            dataset_version_id=uuid.uuid4(),
            dataset_code="trade_volume",
            version="1.0",
            status="active",
            is_default=True,
        )
        session.add(dv)

        # --- Dataset Mapping ---
        import json
        import os
        concept_path = os.path.join(os.path.dirname(__file__), "..", "playground", "dataset-concept.json")
        with open(concept_path, "r", encoding="utf-8") as f:
            server_concept = json.load(f)

        dm = DatasetMapping(
            id=uuid.uuid4(),
            dataset_code="trade_volume",
            version="1.0",
            dataset_concept=server_concept,
        )
        session.add(dm)

        # --- API Keys ---
        pub_key = ApiKey(
            key_id=PUBLIC_KEY_ID,
            client_id="public_client",
            hashed_key=hash_api_key(PUBLIC_KEY_PLAIN),
            status="active",
            tier="standard",
            rate_limit_per_minute=10,
        )
        session.add(pub_key)

        priv_key = ApiKey(
            key_id=PRIVATE_KEY_ID,
            client_id="private_client",
            hashed_key=hash_api_key(PRIVATE_KEY_PLAIN),
            status="active",
            tier="premium",
            rate_limit_per_minute=30,
        )
        session.add(priv_key)

        # --- API Key → Dataset grant (private_client gets explicit access) ---
        grant = ApiKeyDataset(
            id=uuid.uuid4(),
            key_id=PRIVATE_KEY_ID,
            dataset_id=DATASET_ID,
            scopes=["query:read"],
        )
        session.add(grant)

        # --- Cache Policy ---
        cp = CachePolicy(
            id=uuid.uuid4(),
            dataset_id=DATASET_ID,
            ttl_seconds=300,
            enabled=True,
        )
        session.add(cp)

        await session.commit()

    print("=" * 60)
    print("Metadata seeded successfully!")
    print("=" * 60)
    print(f"\nPublic API key  (for dev only): {PUBLIC_KEY_PLAIN}")
    print(f"Private API key (for dev only): {PRIVATE_KEY_PLAIN}")
    print()
    print("Dataset: trade_volume (public, version 1.0)")
    print("Cache: enabled, TTL 300s")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed())
