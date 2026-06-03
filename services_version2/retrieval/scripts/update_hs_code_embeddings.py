"""
Load HS Code Embeddings to Qdrant - UPDATE MODE

Script to embed HS codes from CSV and append them into existing Qdrant collection.
Works independently without PostgreSQL.

Usage:
    python scripts/load_hs_code_embeddings_update.py

Requirements:
    - Qdrant running on QDRANT_HOST:QDRANT_PORT
    - data/processed/structured/hs_code.csv exists
    - sentence-transformers installed

Output:
    - Appends new data to existing 'gdce_hs_code' collection in Qdrant
"""

import os
import sys
import logging
import pandas as pd
from typing import List
from dotenv import load_dotenv

load_dotenv()

try:
    from sentence_transformers import SentenceTransformer
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import PointStruct, VectorParams, Distance
except ImportError as e:
    print(f"❌ Missing required package: {e}")
    print("Install with: pip install sentence-transformers qdrant-client")
    sys.exit(1)

# =====================================================
# LOGGING
# =====================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =====================================================
# CONFIGURATION
# =====================================================
QDRANT_HOST = os.getenv('QDRANT_HOST', '172.25.3.243')
QDRANT_PORT = int(os.getenv('QDRANT_PORT', 6333))
QDRANT_COLLECTION_NAME = 'gdce_hs_code'
EMBEDDING_MODEL = 'all-MiniLM-L6-v2'
BATCH_SIZE_ENCODE = 32
BATCH_SIZE_UPLOAD = 100

HS_CODE_CSV = 'data/processed/structured/hs_code.csv'


# =====================================================
# MAIN SCRIPT
# =====================================================

def validate_inputs() -> bool:
    """Validate that all inputs exist."""
    if not os.path.exists(HS_CODE_CSV):
        logger.error(f"❌ File not found: {HS_CODE_CSV}")
        return False

    logger.info(f"✓ HS Code CSV found: {HS_CODE_CSV}")
    return True


def load_hs_codes() -> pd.DataFrame:
    """Load HS codes from CSV."""
    logger.info("Loading HS code CSV...")
    df = pd.read_csv(HS_CODE_CSV)

    logger.info(f"✓ Loaded {len(df)} HS codes")
    logger.info(f"  Columns: {df.columns.tolist()}")
    logger.info(f"  Sample: {df.iloc[0]['hs_code']} - {df.iloc[0]['description'][:50]}")

    if df.isnull().any().any():
        logger.warning("⚠ Found missing values in CSV")

    duplicates = df['hs_code'].duplicated().sum()
    if duplicates > 0:
        logger.warning(f"⚠ Found {duplicates} duplicate HS codes")

    return df


def initialize_qdrant() -> QdrantClient:
    """Initialize Qdrant client and verify connectivity."""
    logger.info(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}...")

    try:
        client = QdrantClient(
            url=f"http://{QDRANT_HOST}:{QDRANT_PORT}",
            timeout=30.0
        )

        client.get_collections()
        logger.info("✓ Connected to Qdrant")

        return client
    except Exception as e:
        logger.error(f"❌ Failed to connect to Qdrant: {e}")
        logger.error(f"   Is Qdrant running at {QDRANT_HOST}:{QDRANT_PORT}?")
        sys.exit(1)


def load_embedding_model() -> SentenceTransformer:
    """Load embedding model."""
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL}...")

    try:
        model = SentenceTransformer(EMBEDDING_MODEL)
        dim = model.get_sentence_embedding_dimension()
        logger.info(f"✓ Model loaded ({dim}-dimensional)")

        return model
    except Exception as e:
        logger.error(f"❌ Failed to load model: {e}")
        sys.exit(1)


def encode_descriptions(descriptions: List[str], embedder: SentenceTransformer) -> List[List[float]]:
    """Encode descriptions to embeddings."""
    logger.info(f"Encoding {len(descriptions)} descriptions...")
    logger.info(f"  Batch size: {BATCH_SIZE_ENCODE}")

    try:
        embeddings = embedder.encode(
            descriptions,
            batch_size=BATCH_SIZE_ENCODE,
            show_progress_bar=True,
            convert_to_tensor=False
        )

        logger.info(f"✓ Encoded {len(embeddings)} descriptions")

        return [emb.tolist() for emb in embeddings]
    except Exception as e:
        logger.error(f"❌ Encoding failed: {e}")
        sys.exit(1)


def get_existing_point_count(client: QdrantClient) -> int:
    """Get current point count to offset new IDs."""
    try:
        info = client.get_collection(QDRANT_COLLECTION_NAME)
        return info.points_count
    except Exception:
        return 0


def create_points(df: pd.DataFrame, embeddings: List[List[float]]) -> List[PointStruct]:
    """Create Qdrant points from data and embeddings."""
    logger.info("Creating point objects...")

    points = []
    for idx, (_, row) in enumerate(df.iterrows()):
        point = PointStruct(
            id=idx,
            vector=embeddings[idx],
            payload={
                "hs_code": str(row['hs_code']),
                "description": str(row['description']),
                "unit": str(row['unit']) if 'unit' in row else None,
                "cd_rate": float(row['cd_rate']) if 'cd_rate' in row and pd.notna(row['cd_rate']) else None,
                "st_rate": float(row['st_rate']) if 'st_rate' in row and pd.notna(row['st_rate']) else None,
                "vat_rate": float(row['vat_rate']) if 'vat_rate' in row and pd.notna(row['vat_rate']) else None,
                "et_rate": float(row['et_rate']) if 'et_rate' in row and pd.notna(row['et_rate']) else None,
            }
        )
        points.append(point)

    logger.info(f"✓ Created {len(points)} points")
    return points


def upload_points(client: QdrantClient, points: List[PointStruct]) -> None:
    """Upload points to existing Qdrant collection - APPEND only."""
    start_id = get_existing_point_count(client)
    logger.info(f"Collection has {start_id} existing points — appending {len(points)} new points...")

    try:
        for i in range(0, len(points), BATCH_SIZE_UPLOAD):
            batch = points[i:i + BATCH_SIZE_UPLOAD]

            # Offset IDs so we don't overwrite existing points
            for point in batch:
                point.id = start_id + point.id

            client.upsert(
                collection_name=QDRANT_COLLECTION_NAME,
                points=batch
            )

            progress = min(i + BATCH_SIZE_UPLOAD, len(points))
            logger.info(f"  Uploaded {progress}/{len(points)} points")

        logger.info(f"✓ Done — total points now: {start_id + len(points)}")
    except Exception as e:
        logger.error(f"❌ Upload failed: {e}")
        sys.exit(1)


def verify_collection(client: QdrantClient) -> None:
    """Verify collection loaded correctly."""
    logger.info("Verifying collection...")

    try:
        info = client.get_collection(QDRANT_COLLECTION_NAME)
        logger.info(f"✓ Collection verified:")
        logger.info(f"  Points: {info.points_count}")
        logger.info(f"  Vector size: {info.config.params.vectors.size}")

        logger.info("Testing semantic search...")
        test_query = "ceramic tiles"
        embedder = SentenceTransformer(EMBEDDING_MODEL)
        query_vector = embedder.encode(test_query).tolist()

        results = client.search(
            collection_name=QDRANT_COLLECTION_NAME,
            query_vector=query_vector,
            limit=3,
            score_threshold=0.3
        )

        logger.info(f"✓ Search test passed:")
        for result in results:
            logger.info(f"    {result.payload['hs_code']}: {result.payload['description'][:40]}... (score: {result.score:.3f})")

    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        logger.warning("⚠ Search test failed, but collection may still be valid")


def main():
    """Main execution."""
    logger.info("=" * 60)
    logger.info("HS Code Embeddings Loader - UPDATE MODE")
    logger.info("=" * 60)

    # Step 1: Validate
    if not validate_inputs():
        sys.exit(1)

    # Step 2: Load data
    df = load_hs_codes()

    # Step 3: Initialize Qdrant
    client = initialize_qdrant()

    # Step 4: Load embedding model
    embedder = load_embedding_model()

    # Step 5: Encode descriptions
    embeddings = encode_descriptions(df['description'].tolist(), embedder)

    # Step 6: Create points
    points = create_points(df, embeddings)

    # Step 7: Upload (append to existing collection)
    upload_points(client, points)

    # Step 8: Verify
    verify_collection(client)

    logger.info("=" * 60)
    logger.info("✅ Successfully appended HS code embeddings to Qdrant!")
    logger.info("=" * 60)
    logger.info("\nYou can now test with:")
    logger.info("  curl -X POST http://127.0.0.1:8004/hs-lookup \\")
    logger.info("    -H 'Content-Type: application/json' \\")
    logger.info("    -d '{\"description\": \"ceramic tiles\", \"limit\": 5}'")


if __name__ == "__main__":
    main()