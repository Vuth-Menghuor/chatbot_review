#!/usr/bin/env python
"""
Upload RAG documents to remote Qdrant server (172.25.3.243)
======================================================
"""

import json
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

load_dotenv()


class RAGDocumentLoaderRemoteUpdate:
    """Load RAG documents into remote Qdrant - UPDATE MODE (no delete)"""
    
    def __init__(self):
        self.qdrant_url = "https://172.25.3.243:6333"
        self.collection_name = "gdce_docs"
        self.embedding_model = os.getenv("QUERY_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self.chunk_size = 200
        self.chunk_overlap = 50
        
        print(f"Using embedding model: {self.embedding_model}")
        self.embedder = SentenceTransformer(self.embedding_model)
        self.qdrant_client = QdrantClient(url=self.qdrant_url)
    
    def load_documents(self):
        """Load all markdown documents"""
        docs_dir = Path("data/processed/rag_text/cleaned_docs")
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
        
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        
        chunks = []
        i = 0
        
        while i < len(paragraphs):
            para = paragraphs[i]
            
            current_chunk = para
            current_len = len(para)
            
            if re.match(r'^#+\s', para):
                current_level = len(re.match(r'^#+', para).group())
                
                j = i + 1
                while j < len(paragraphs) and current_len < self.chunk_size:
                    next_para = paragraphs[j]
                    
                    if re.match(r'^#+\s', next_para):
                        next_level = len(re.match(r'^#+', next_para).group())
                        if next_level <= current_level:
                            break
                        if next_level < current_level - 1:
                            break
                    
                    combined_len = current_len + len(next_para) + 2
                    if combined_len > self.chunk_size:
                        break
                    
                    current_chunk += "\n\n" + next_para
                    current_len = combined_len
                    j += 1
                
                i = j if j > i + 1 else i + 1
            else:
                j = i + 1
                while j < len(paragraphs) and current_len < self.chunk_size:
                    next_para = paragraphs[j]
                    if re.match(r'^#+\s', next_para):
                        break
                    
                    combined_len = current_len + len(next_para) + 2
                    if combined_len > self.chunk_size:
                        break
                    
                    current_chunk += "\n\n" + next_para
                    current_len = combined_len
                    j += 1
                
                i = j if j > i + 1 else i + 1
            
            if len(current_chunk.strip()) > 5:
                lines = current_chunk.strip().split('\n')
                content_lines = [l for l in lines if l.strip() and not re.match(r'^#+\s', l)]
                if content_lines:
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
    
    def create_embeddings(self, chunks):
        """Create vector embeddings for chunks"""
        print("Creating embeddings...", end=" ", flush=True)
        texts = [chunk["text"] for chunk in chunks]
        embeddings = self.embedder.encode(texts, show_progress_bar=True)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding.tolist()
        
        return chunks
    
    def get_existing_point_count(self):
        """Get the current highest point ID in the collection"""
        try:
            collection_info = self.qdrant_client.get_collection(self.collection_name)
            return collection_info.points_count
        except Exception:
            return 0

    def upload_to_qdrant(self, chunks):
        """Upload chunks to remote Qdrant - ADD to existing collection"""
        print("Uploading to remote Qdrant (172.25.3.243)...", end=" ", flush=True)
        
        try:
            # Check if collection exists, create if not
            existing_collections = [c.name for c in self.qdrant_client.get_collections().collections]
            
            if self.collection_name not in existing_collections:
                if chunks and "embedding" in chunks[0]:
                    embedding_dim = len(chunks[0]["embedding"])
                    self.qdrant_client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=VectorParams(size=embedding_dim, distance=Distance.COSINE),
                    )
                    print(f"\n  [...] Created new collection '{self.collection_name}' with {embedding_dim}-dim vectors")
                start_id = 0
            else:
                # Collection exists — get current point count to offset new IDs
                start_id = self.get_existing_point_count()
                print(f"\n  [...] Collection '{self.collection_name}' exists with {start_id} points — appending new data")
            
            # Upload points with offset IDs to avoid overwriting existing ones
            points = [
                PointStruct(
                    id=start_id + i,
                    vector=chunk["embedding"],
                    payload={
                        "doc_id": chunk["doc_id"],
                        "filename": chunk["filename"],
                        "text": chunk["text"],
                        "chunk_idx": chunk["chunk_idx"]
                    }
                )
                for i, chunk in enumerate(chunks)
            ]
            
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            
            print(f"[OK] Added {len(chunks)} new chunks — total points now: {start_id + len(chunks)}\n")
        
        except Exception as e:
            print(f"\n[ERROR] Error uploading to Qdrant: {e}")
            raise
    
    def load_all(self):
        """Load all documents to remote Qdrant - UPDATE MODE"""
        print("\n" + "="*80)
        print("RAG DOCUMENT LOADER - REMOTE QDRANT (UPDATE MODE)")
        print("Target: 172.25.3.243:6333")
        print("="*80 + "\n")
        
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
        
        # Step 3: Create embeddings
        print("3. Creating Embeddings...")
        all_chunks = self.create_embeddings(all_chunks)
        print(f"[OK] Embeddings created\n")
        
        # Step 4: Upload to remote Qdrant
        print("4. Uploading to Remote Qdrant (UPDATE MODE)...")
        self.upload_to_qdrant(all_chunks)
        
        print("="*80)
        print("[OK] RAG DOCUMENT UPDATE COMPLETE")
        print("="*80 + "\n")


if __name__ == "__main__":
    loader = RAGDocumentLoaderRemoteUpdate()
    loader.load_all()