"""
Upload gdce_docs.json → local Qdrant (localhost:6334)
Collection: gdce_docs
Vector dim: 1024 (e5-large-v2)
"""

import json
import time
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

# ── Config ────────────────────────────────────────────────────────────────────
JSON_PATH       = "gdce_docs.json"
COLLECTION_NAME = "gdce_docs"
VECTOR_DIM      = 1024
BATCH_SIZE      = 128
QDRANT_URL      = "http://localhost"
QDRANT_PORT     = 6334
# ─────────────────────────────────────────────────────────────────────────────


def load_data(path: str) -> list[dict]:
    print(f"Loading {path} …")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    print(f"  → {len(data):,} points loaded")
    return data


def ensure_collection(client: QdrantClient) -> None:
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        print(f"Collection '{COLLECTION_NAME}' already exists — skipping create.")
        return

    print(f"Creating collection '{COLLECTION_NAME}' (dim={VECTOR_DIM}, cosine) …")
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    print("  → Done.")


def upload(client: QdrantClient, data: list[dict]) -> None:
    total   = len(data)
    batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Uploading {total:,} points in {batches} batches (batch_size={BATCH_SIZE}) …")

    start = time.time()
    for i in range(batches):
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
        done    = min((i + 1) * BATCH_SIZE, total)
        elapsed = time.time() - start
        print(f"  [{done:>5}/{total}]  batch {i+1}/{batches}  ({elapsed:.1f}s)")

    print(f"\n✓ Upload complete in {time.time() - start:.1f}s")


def verify(client: QdrantClient) -> None:
    info  = client.get_collection(COLLECTION_NAME)
    count = info.points_count
    print(f"✓ Collection '{COLLECTION_NAME}' now has {count:,} points.")


def main() -> None:
    data   = load_data(JSON_PATH)
    client = QdrantClient(url=QDRANT_URL, port=QDRANT_PORT)
    ensure_collection(client)
    upload(client, data)
    verify(client)


if __name__ == "__main__":
    main()