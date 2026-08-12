#!/usr/bin/env python
"""
Chunk + embed PDF documents, save to JSON (no Qdrant upload)
==============================================================

Run this first. It extracts text from PDFs, chunks them, embeds the
chunks, and writes everything (text + metadata + embedding vectors)
to a JSON file. Nothing touches Qdrant in this step — so you can
inspect/review the chunks before committing them to your collection.

Install requirement:
    pip install pymupdf
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import fitz  # PyMuPDF
from typing import List, Dict

load_dotenv()


class PDFChunkEmbedder:
    """Chunk + embed PDFs, save output to JSON for later upload."""

    def __init__(self):
        self.embedding_model = os.getenv("QUERY_EMBEDDING_MODEL", "BAAI/bge-m3")

        # Keep consistent with your markdown loader's chunk_size if you
        # want retrieval scoring to stay comparable across sources.
        self.chunk_size = 200
        self.chunk_overlap = 50

        self.encode_batch_size = int(os.getenv("EMBED_BATCH_SIZE", "8"))
        self.max_seq_length = int(os.getenv("EMBED_MAX_SEQ_LENGTH", "512"))

        print(f"Using embedding model: {self.embedding_model}")
        print(f"Chunk size: {self.chunk_size}, Overlap: {self.chunk_overlap}")

        self.embedder = SentenceTransformer(self.embedding_model)
        self.embedder.max_seq_length = self.max_seq_length

    # ------------------------------------------------------------------
    # PDF loading + extraction (page-aware)
    # ------------------------------------------------------------------
    def load_pdfs(self, pdf_dir="data_pdf/") -> List[Dict]:
        pdf_dir = Path(pdf_dir)
        documents = []

        for pdf_file in sorted(pdf_dir.glob("*.pdf")):
            print(f"  Reading {pdf_file.name}...")
            try:
                doc = fitz.open(pdf_file)
                pages = []
                for page_num in range(len(doc)):
                    text = doc[page_num].get_text("text").strip()
                    if text:
                        pages.append({"page_number": page_num + 1, "text": text})
                doc.close()

                if pages:
                    documents.append({
                        "id": pdf_file.stem,
                        "filename": pdf_file.name,
                        "pages": pages,
                    })
                else:
                    print(f"  [!] No text extracted from {pdf_file.name} (scanned/image PDF?)")
            except Exception as e:
                print(f"  [ERROR] Failed to read {pdf_file.name}: {e}")

        print(f"[OK] Loaded {len(documents)} PDF documents\n")
        return documents

    # ------------------------------------------------------------------
    # Chunking: paragraph-based, sentence-level fallback for oversized
    # paragraphs, real overlap between chunks.
    # ------------------------------------------------------------------
    def chunk_document(self, doc: Dict) -> List[Dict]:
        chunks = []
        chunk_idx = 0

        for page in doc["pages"]:
            raw = page["text"].replace("\r", "")
            paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]
            if len(paragraphs) <= 1:
                paragraphs = [p.strip() for p in raw.split("\n") if p.strip()]

            current = ""

            def flush(text):
                nonlocal chunk_idx
                if len(text.strip()) > 5:
                    chunks.append({
                        "doc_id": doc["id"],
                        "filename": doc["filename"],
                        "text": text.strip(),
                        "chunk_idx": chunk_idx,
                        "page_number": page["page_number"],
                        "source_type": "pdf",
                    })
                    chunk_idx += 1

            for para in paragraphs:
                if len(para) > self.chunk_size * 1.5:
                    if current:
                        flush(current)
                        current = current[-self.chunk_overlap:]
                    sentences = re.split(r'(?<=[.!?])\s+', para)
                    for sentence in sentences:
                        candidate = (current + " " + sentence).strip() if current else sentence
                        if len(candidate) > self.chunk_size and current:
                            flush(current)
                            overlap = current[-self.chunk_overlap:]
                            current = (overlap + " " + sentence).strip()
                        else:
                            current = candidate
                    continue

                candidate = (current + "\n\n" + para).strip() if current else para
                if len(candidate) <= self.chunk_size:
                    current = candidate
                else:
                    flush(current)
                    overlap = current[-self.chunk_overlap:] if current else ""
                    current = (overlap + "\n\n" + para).strip() if overlap else para

            flush(current)

        return chunks

    # ------------------------------------------------------------------
    # Embed one file's chunks, sub-batched, with progress printed as it goes
    # ------------------------------------------------------------------
    def embed_file_chunks(self, chunks: List[Dict]) -> List[Dict]:
        texts = [c["text"] for c in chunks]
        bs = self.encode_batch_size
        for start in range(0, len(texts), bs):
            batch_texts = texts[start:start + bs]
            batch_embeddings = self.embedder.encode(
                batch_texts,
                batch_size=bs,
                show_progress_bar=False,
            )
            for i, embedding in enumerate(batch_embeddings):
                chunks[start + i]["embedding"] = embedding.tolist()
            done = min(start + bs, len(texts))
            print(f"\r    embedding {done}/{len(texts)} chunks...", end="", flush=True)
        print()  # newline after this file's progress line
        return chunks

    def _save_progress(self, output_path, all_chunks, files_done, files_total):
        output = {
            "embedding_model": self.embedding_model,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "created_at": datetime.now().isoformat(),
            "files_done": files_done,
            "files_total": files_total,
            "chunk_count": len(all_chunks),
            "chunks": all_chunks,
        }
        # Write to a temp file then replace, so a crash mid-write never
        # corrupts the last good save.
        tmp_path = str(output_path) + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, output_path)

    def run(self, pdf_dir="data_pdf/", output_path="pdf_chunks_embedded.json"):
        print("\n" + "=" * 80)
        print("PDF CHUNK + EMBED (saving to JSON, no upload)")
        print("=" * 80 + "\n")

        print("1. Loading PDFs...")
        documents = self.load_pdfs(pdf_dir)
        if not documents:
            print("[!] No PDFs found — nothing to do.")
            return

        print("2. Chunking + embedding, one file at a time...\n")
        all_chunks = []
        total_files = len(documents)
        start_time = datetime.now()

        for idx, doc in enumerate(documents, start=1):
            chunks = self.chunk_document(doc)
            if not chunks:
                print(f"[{idx}/{total_files}] {doc['filename']}: 0 chunks, skipping")
                continue

            print(f"[{idx}/{total_files}] {doc['filename']}: {len(chunks)} chunks")
            chunks = self.embed_file_chunks(chunks)
            all_chunks.extend(chunks)

            # Save after every file so a crash/network drop only costs
            # you the file in progress, not the whole run.
            self._save_progress(output_path, all_chunks, idx, total_files)

            elapsed = (datetime.now() - start_time).total_seconds()
            avg_per_file = elapsed / idx
            remaining = avg_per_file * (total_files - idx)
            print(
                f"    saved progress ({len(all_chunks)} chunks so far) "
                f"— est. {remaining/60:.1f} min remaining\n"
            )

        print("=" * 80)
        print(f"[OK] Saved {len(all_chunks)} embedded chunks to {output_path}")
        print("DONE — review the JSON, then run the upload script when ready.")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    embedder = PDFChunkEmbedder()
    embedder.run(pdf_dir="data_pdf/", output_path="pdf_chunks_embedded.json")