"""
HS Code Data Uploader — Seeds the Qdrant vector store.

Reads a local JSON file containing pre-embedded HS code documents and
uploads them in batches to a local Qdrant instance. Run this once after
``docker compose up -d`` to populate the ``gdce_hs_code`` collection
before the retrieval service can serve queries.

Usage
-----
    python scripts/hs_code.py

Prerequisites
-------------
1. Qdrant must be running: ``docker compose up -d qdrant``
2. The JSON data file (``gdce_hs_code.json``) must exist in the
   ``scripts/`` directory.

Data Format
-----------
The JSON file should be a list of objects, each with:

.. code-block:: json

    {
        "id": "unique-point-id",
        "vector": [0.123, -0.456, ...],   // 384-dimensional embedding
        "payload": {
            "hs_code": "8703.23.10",
            "description": "Motor cars, spark-ignition engine...",
            "title": "...",
            "text": "..."
        }
    }
"""

import json
import time
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    PointStruct,
)

# =========================================================================
# Configuration
# =========================================================================
# Adjust these to match your environment and data file name.

JSON_PATH       = "gdce_hs_code.json"   # Path to the pre-embedded JSON file
COLLECTION_NAME = "gdce_hs_code"        # Must match QDRANT_HS_CODE_COLLECTION in .env
VECTOR_DIM      = 384                   # Embedding dimension (all-MiniLM-L6-v2)
BATCH_SIZE      = 256                   # Points per upsert call — tune for memory
QDRANT_URL      = "http://localhost"    # Qdrant REST endpoint
QDRANT_PORT     = 6333                  # Qdrant REST port
# =========================================================================


def load_data(path: str) -> list[dict]:
    """
    Load the HS code data from a JSON file.

    Parameters
    ----------
    path : str
        Path to the JSON file relative to the working directory.

    Returns
    -------
    list[dict]
        List of point dicts, each with ``id``, ``vector``, and ``payload``.
    """
    print(f"Loading {path} …")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    print(f"  → {len(data):,} points loaded")
    return data


def ensure_collection(client: QdrantClient) -> None:
    """
    Create the HS code collection if it doesn't already exist.

    Uses cosine distance — the standard for sentence-transformer embeddings.
    If the collection already exists the operation is a no-op.
    """
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        print(f"Collection '{COLLECTION_NAME}' already exists — skipping create.")
        return

    print(
        f"Creating collection '{COLLECTION_NAME}' "
        f"(dim={VECTOR_DIM}, cosine) …"
    )
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    print("  → Done.")


def upload(client: QdrantClient, data: list[dict]) -> None:
    """
    Upload all HS code points to Qdrant in batches.

    Batched upserts keep memory usage bounded and provide progress feedback
    for large datasets.
    """
    total   = len(data)
    batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(
        f"Uploading {total:,} points in {batches} batches "
        f"(batch_size={BATCH_SIZE}) …"
    )

    start = time.time()
    for i in range(batches):
        # Slice the current batch.
        chunk = data[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
        points = [
            PointStruct(
                id=item["id"],
                vector=item["vector"],
                payload=item["payload"],
            )
            for item in chunk
        ]
        client.upsert(collection_name=COLLECTION_NAME, points=points)

        done = min((i + 1) * BATCH_SIZE, total)
        elapsed = time.time() - start
        print(f"  [{done:>6}/{total}]  batch {i+1}/{batches}  ({elapsed:.1f}s)")

    print(f"\n✓ Upload complete in {time.time() - start:.1f}s")


def verify(client: QdrantClient) -> None:
    """
    Confirm the collection point count matches expectations.

    Prints the final point count for operator confidence.
    """
    info = client.get_collection(COLLECTION_NAME)
    count = info.points_count
    print(f"✓ Collection '{COLLECTION_NAME}' now has {count:,} points.")


def main() -> None:
    """
    Entry point — load, ensure collection, upload, verify.

    Steps:
    1. Load the JSON data file.
    2. Connect to the local Qdrant instance.
    3. Create the collection (no-op if it already exists).
    4. Batch-upload all points.
    5. Verify the final point count.
    """
    data   = load_data(JSON_PATH)
    client = QdrantClient(url=QDRANT_URL, port=QDRANT_PORT)
    ensure_collection(client)
    upload(client, data)
    verify(client)


if __name__ == "__main__":
    main()