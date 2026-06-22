#!/usr/bin/env python
"""
Upload RAG documents to the General Retrieval Service's Qdrant instance
======================================================

Memory-safe version: encodes and uploads in small groups instead of
embedding the entire corpus in one call. This avoids OOM kills on
CPU-only machines when using larger embedding models like BAAI/bge-m3.
"""

import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

load_dotenv()


class RAGDocumentLoaderRemote:
    """Load RAG documents into the general service's dedicated Qdrant instance"""

    def __init__(self):
        self.qdrant_url = "http://localhost:6334"  # General service's dedicated Qdrant instance
        self.collection_name = "gdce_docs"
        # Use same embedding model as the general retrieval service - from environment variable
        self.embedding_model = os.getenv("QUERY_EMBEDDING_MODEL", "BAAI/bge-m3")
        self.chunk_size = 200
        self.chunk_overlap = 50

        # --- Memory-safety knobs ---
        # How many texts sentence-transformers embeds in a single forward pass.
        # Lower = less peak RAM, slower throughput. Override with EMBED_BATCH_SIZE.
        self.encode_batch_size = int(os.getenv("EMBED_BATCH_SIZE", "8"))
        # Cap tokenized sequence length. Our chunks are ~200 chars, so bge-m3's
        # default 8192-token window is unnecessary and wastes memory/compute.
        self.max_seq_length = int(os.getenv("EMBED_MAX_SEQ_LENGTH", "512"))
        # How many chunks to encode + upsert together before moving to the next
        # group. Keeps total in-memory text/embedding footprint small and gives
        # incremental progress in Qdrant as the run proceeds.
        self.upload_group_size = int(os.getenv("UPLOAD_GROUP_SIZE", "200"))

        print(f"Using embedding model: {self.embedding_model}")
        print(
            f"encode_batch_size={self.encode_batch_size} "
            f"max_seq_length={self.max_seq_length} "
            f"upload_group_size={self.upload_group_size}"
        )

        self.embedder = SentenceTransformer(self.embedding_model)
        self.embedder.max_seq_length = self.max_seq_length

        self.qdrant_client = QdrantClient(url=self.qdrant_url)

    def load_documents(self):
        """Load all markdown documents"""
        docs_dir = Path("data/")
        documents = []

        for md_file in sorted(docs_dir.glob("*.md")):
            print(f"  Reading {md_file.name}...")
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
                documents.append({
                    "id": md_file.stem,
                    "filename": md_file.name,
                    "content": content,
                    "loaded_at": datetime.now().isoformat()
                })

        print(f"[OK] Loaded {len(documents)} documents\n")
        return documents

    def chunk_document(self, doc):
        """Split document into smaller, focused chunks at section boundaries"""
        import re
        content = doc["content"]

        # Split by blank lines to get paragraphs
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

        chunks = []
        i = 0

        while i < len(paragraphs):
            para = paragraphs[i]

            # Start a new chunk
            current_chunk = para
            current_len = len(para)

            # If this is a header, gather its immediate content only
            if re.match(r'^#+\s', para):
                current_level = len(re.match(r'^#+', para).group())

                # Look ahead to add related content
                j = i + 1
                while j < len(paragraphs) and current_len < self.chunk_size:
                    next_para = paragraphs[j]

                    # If next is a header, stop if it's same level or higher (fewer #'s)
                    if re.match(r'^#+\s', next_para):
                        next_level = len(re.match(r'^#+', next_para).group())
                        # Stop at same level or higher
                        if next_level <= current_level:
                            break
                        # Also stop if it's MUCH lower level (e.g., #### stops at ##)
                        # This prevents major sections from bleeding in
                        if next_level < current_level - 1:
                            break

                    # Add to chunk
                    combined_len = current_len + len(next_para) + 2
                    if combined_len > self.chunk_size:
                        break

                    current_chunk += "\n\n" + next_para
                    current_len = combined_len
                    j += 1

                i = j if j > i + 1 else i + 1
            else:
                # For non-header paragraphs, just take until size limit
                j = i + 1
                while j < len(paragraphs) and current_len < self.chunk_size:
                    next_para = paragraphs[j]
                    # Stop at any header
                    if re.match(r'^#+\s', next_para):
                        break

                    combined_len = current_len + len(next_para) + 2
                    if combined_len > self.chunk_size:
                        break

                    current_chunk += "\n\n" + next_para
                    current_len = combined_len
                    j += 1

                i = j if j > i + 1 else i + 1

            # Save chunk if it has content
            if len(current_chunk.strip()) > 5:
                lines = current_chunk.strip().split('\n')
                # Check if this is just headers/titles without actual content
                content_lines = [l for l in lines if l.strip() and not re.match(r'^#+\s', l)]
                if content_lines:  # Only add if there's non-header content
                    chunks.append(current_chunk.strip())

        return [
            {
                "doc_id": doc["id"],
                "filename": doc["filename"],
                "text": chunk,
                "chunk_idx": idx
            }
            for idx, chunk in enumerate(chunks)
        ]

    def _ensure_collection(self, vector_dim: int):
        """Delete any existing collection and recreate it at the correct dimension."""
        try:
            self.qdrant_client.delete_collection(self.collection_name)
            print(f"  [...] Deleted existing '{self.collection_name}' collection")
        except Exception:
            pass

        self.qdrant_client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
        )
        print(f"  [...] Created new collection with {vector_dim}-dim vectors")

    def encode_and_upload(self, all_chunks):
        """
        Encode and upload chunks in small groups to keep peak memory low.
        The collection is created once, sized from the first group's embedding
        dimension, then subsequent groups are upserted incrementally.
        """
        total = len(all_chunks)
        group_size = self.upload_group_size
        collection_ready = False
        point_id = 0

        for start in range(0, total, group_size):
            group = all_chunks[start:start + group_size]
            texts = [c["text"] for c in group]

            print(
                f"  Encoding chunks {start + 1}-{min(start + group_size, total)} "
                f"of {total}...",
                end=" ",
                flush=True,
            )
            embeddings = self.embedder.encode(
                texts,
                batch_size=self.encode_batch_size,
                show_progress_bar=False,
            )
            print("done")

            if not collection_ready:
                self._ensure_collection(vector_dim=len(embeddings[0]))
                collection_ready = True

            points = []
            for chunk, embedding in zip(group, embeddings):
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=embedding.tolist(),
                        payload={
                            "doc_id": chunk["doc_id"],
                            "filename": chunk["filename"],
                            "text": chunk["text"],
                            "chunk_idx": chunk["chunk_idx"],
                        },
                    )
                )
                point_id += 1

            self.qdrant_client.upsert(collection_name=self.collection_name, points=points)
            print(f"  [OK] Uploaded {len(points)} chunks (running total: {point_id}/{total})")

            # Drop references so this group's memory can be reclaimed before the next one.
            del embeddings, points, texts, group

        print(f"\n[OK] Uploaded {point_id} chunks total to Qdrant\n")

    def load_all(self):
        """Load all documents, then encode + upload incrementally"""
        print("\n" + "=" * 80)
        print("RAG DOCUMENT LOADER - GENERAL SERVICE QDRANT")
        print(f"Target: {self.qdrant_url}")
        print("=" * 80 + "\n")

        # Step 1: Load documents
        print("1. Loading Documents...")
        documents = self.load_documents()

        # Step 2: Chunk documents
        print("2. Chunking Documents...")
        all_chunks = []
        for doc in documents:
            chunks = self.chunk_document(doc)
            all_chunks.extend(chunks)
            print(f"  {doc['id']}: {len(chunks)} chunks")
        print(f"[OK] Total: {len(all_chunks)} chunks\n")

        # Step 3 + 4 combined: encode and upload in memory-safe groups
        print("3. Encoding + Uploading (incremental, memory-safe)...")
        self.encode_and_upload(all_chunks)

        print("=" * 80)
        print("[OK] RAG DOCUMENT LOADING COMPLETE")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    loader = RAGDocumentLoaderRemote()
    loader.load_all()