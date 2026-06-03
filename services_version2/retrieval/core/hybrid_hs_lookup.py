import logging
from typing import Dict, List, Any, Optional

try:
    from ..config import RetrievalConfig
except ImportError:
    from config import RetrievalConfig
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class HybridHSLookup:
    """
    Hybrid HS code lookup using Qdrant semantic search.
    """
    def __init__(self, config: Optional[RetrievalConfig] = None):
        self.config = config or RetrievalConfig()
        self.qdrant_host = self.config.qdrant_host
        self.qdrant_port = self.config.qdrant_port
        self.qdrant_collection = self.config.qdrant_hs_code_collection
        self.embedding_model = self.config.query_embedding_model
        self.embedder = SentenceTransformer(self.embedding_model)
        self.qdrant = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)

    def semantic_search(self, description: str, top_k: int = 3) -> List[Dict[str, Any]]:
        vector = self.embedder.encode(description, convert_to_tensor=False).tolist()
        results = self.qdrant.search(
            collection_name=self.qdrant_collection,
            query_vector=vector,
            limit=top_k,
            with_payload=True
        )
        return [
            {
                "hs_code": r.payload.get("hs_code") if r.payload else None,
                "description": r.payload.get("description") if r.payload else None,
                "similarity": float(r.score),
                "vector_id": r.id
            }
            for r in results
        ]

    def answer_lookup(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        logger.info(f"Hybrid HS lookup: '{query}'")
        hs_results = self.semantic_search(query, top_k=top_k)
        response = {
            "intent": "answer_lookup",
            "query": query,
            "hs_codes": [],
            "total_matches": len(hs_results),
            "data_sources": {
                "hs_lookup": "Qdrant (semantic)",
                "embedding_model": self.embedding_model,
                "qdrant_collection": self.qdrant_collection
            }
        }
        for idx, result in enumerate(hs_results, 1):
            hs_code = result["hs_code"]
            response["hs_codes"].append({
                "rank": idx,
                "hs_code": hs_code,
                "description": result["description"],
                "confidence": result["similarity"]
            })
        return response
