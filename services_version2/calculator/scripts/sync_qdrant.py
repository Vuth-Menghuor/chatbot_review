#!/usr/bin/env python3
"""
Calculator Service — Qdrant Sync Script
=======================================
Re-builds the Qdrant `gdce_hs_code` collection from the calculator's
own PostgreSQL database.

This guarantees that the embedding model used for indexing is exactly
the same as the one used for querying (`QDRANT_EMBEDDING_MODEL`).

Usage:
    python scripts/sync_qdrant.py

Environment:
    QDRANT_HOST         — Qdrant server host (default: localhost)
    QDRANT_PORT         — Qdrant server port (default: 6333)
    QDRANT_EMBEDDING_MODEL — sentence-transformers model (default: all-MiniLM-L6-v2)
    CALCULATOR_DB_*     — PostgreSQL connection params
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load calculator .env
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_DUTY_COLLECTION", "gdce_hs_code")
EMBEDDING_MODEL = os.getenv("QDRANT_EMBEDDING_MODEL", "all-MiniLM-L6-v2")

DB_HOST = os.getenv("CALCULATOR_DB_HOST", "localhost")
DB_PORT = int(os.getenv("CALCULATOR_DB_PORT", "5432"))
DB_NAME = os.getenv("CALCULATOR_DB_NAME", "gdce_calculator")
DB_USER = os.getenv("CALCULATOR_DB_USER", "calc_app")
DB_PASSWORD = os.getenv("CALCULATOR_DB_PASSWORD", "")

BATCH_SIZE = 256


def get_pg_connection():
    import psycopg2
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=10,
    )


def fetch_hs_data():
    """Pull active HS codes + duty rates from PostgreSQL."""
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            hs.hs_code,
            hs.description,
            hs.unit,
            dr.cd_rate,
            dr.st_rate,
            dr.vat_rate,
            dr.et_rate,
            dr.atp_rate
        FROM hs_codes hs
        LEFT JOIN duty_rates dr
            ON dr.hs_code = hs.hs_code
            AND dr.is_active = TRUE
            AND (dr.end_date IS NULL OR dr.end_date > CURRENT_DATE)
            AND dr.effective_date <= CURRENT_DATE
        WHERE hs.is_active = TRUE
          AND (hs.end_date IS NULL OR hs.end_date > CURRENT_DATE)
        ORDER BY hs.hs_code
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def recreate_collection(client, vector_size: int):
    """Drop and re-create the Qdrant collection."""
    from qdrant_client.models import Distance, VectorParams

    collections = [c.name for c in client.get_collections().collections]
    if QDRANT_COLLECTION in collections:
        logger.info(f"Deleting existing collection '{QDRANT_COLLECTION}'...")
        client.delete_collection(QDRANT_COLLECTION)

    logger.info(
        f"Creating collection '{QDRANT_COLLECTION}' with "
        f"vector_size={vector_size}, distance=Cosine"
    )
    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def sync():
    try:
        from sentence_transformers import SentenceTransformer
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.error("Run: pip install sentence-transformers qdrant-client psycopg2-binary python-dotenv")
        sys.exit(1)

    # 1. Load embedder
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
    embedder = SentenceTransformer(EMBEDDING_MODEL)
    vector_size = embedder.get_sentence_embedding_dimension()
    logger.info(f"Model dimension: {vector_size}")

    # 2. Connect Qdrant
    logger.info(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}...")
    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=30)
    try:
        qdrant.get_collections()
    except Exception as e:
        logger.error(f"Cannot reach Qdrant: {e}")
        sys.exit(1)

    # 3. Fetch data from PostgreSQL
    logger.info(f"Fetching HS codes from PostgreSQL ({DB_HOST}:{DB_PORT}/{DB_NAME})...")
    rows = fetch_hs_data()
    if not rows:
        logger.error("No HS codes found in PostgreSQL. Run init_db.py first.")
        sys.exit(1)
    logger.info(f"Fetched {len(rows)} rows")

    # 4. Recreate collection
    recreate_collection(qdrant, vector_size)

    # 5. Build points and upsert in batches
    points: list[PointStruct] = []
    descriptions = [row[1] or "" for row in rows]

    logger.info("Embedding descriptions (this may take a minute)...")
    embeddings = embedder.encode(descriptions, show_progress_bar=True, batch_size=BATCH_SIZE)

    for idx, (row, vector) in enumerate(zip(rows, embeddings), start=1):
        hs_code, description, unit, cd_rate, st_rate, vat_rate, et_rate, atp_rate = row
        # Qdrant payload stores rates as integers 0-100 for historical compatibility
        payload = {
            "hs_code": hs_code,
            "description": description or "",
            "unit": unit or "u",
            "cd_rate": int((cd_rate or 0) * 100),
            "st_rate": int((st_rate or 0) * 100),
            "vat_rate": int((vat_rate or 0) * 100),
            "et_rate": int((et_rate or 0) * 100),
            "atp_rate": float(atp_rate or 0),
        }
        points.append(
            PointStruct(id=idx, vector=vector.tolist(), payload=payload)
        )

    total = len(points)
    logger.info(f"Upserting {total} points into Qdrant...")
    for i in range(0, total, BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        qdrant.upsert(collection_name=QDRANT_COLLECTION, points=batch)
        logger.info(f"  Upserted {min(i + BATCH_SIZE, total)}/{total}")

    # 6. Verify
    count = qdrant.count(collection_name=QDRANT_COLLECTION).count
    logger.info(f"Collection '{QDRANT_COLLECTION}' now contains {count} points")

    # Quick sanity search (version-agnostic: query_points for qdrant-client >=1.10,
    # search for older versions)
    test_query = "car"
    test_vec = embedder.encode(test_query, convert_to_tensor=False).tolist()
    if hasattr(qdrant, "query_points"):
        results = qdrant.query_points(
            collection_name=QDRANT_COLLECTION,
            query=test_vec,
            limit=3,
            with_payload=True,
        )
        points = results.points if results else []
    else:
        points = qdrant.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=test_vec,
            limit=3,
            with_payload=True,
        )
    logger.info(f"Sanity search for '{test_query}':")
    for p in points:
        payload = p.payload or {}
        logger.info(
            f"  score={p.score:.3f}  {payload.get('hs_code')} — {payload.get('description')}"
        )

    logger.info("Sync complete.")


if __name__ == "__main__":
    sync()
