from sentence_transformers import SentenceTransformer
import os
import logging

logger = logging.getLogger(__name__)

class MiniLMEmbeddingService:
    """Service for generating embeddings using all-MiniLM-L12-v2"""
    
    def __init__(self):
        self.model_name = os.getenv('INTENT_DETECTION_MODEL', 'all-MiniLM-L12-v2')
        logger.info(f"Loading {self.model_name} model...")
        self.model = SentenceTransformer(self.model_name)
        logger.info(f"✓ {self.model_name} loaded successfully")
    
    def encode_query(self, text: str):
        """Generate embedding for a query"""
        return self.model.encode(text, convert_to_tensor=False)
    
    def similarity(self, text1: str, text2: str) -> float:
        """Compute similarity between two texts"""
        from sentence_transformers.util import pytorch_cos_sim
        embeddings = self.model.encode([text1, text2])
        similarity = pytorch_cos_sim(embeddings[0], embeddings[1]).item()
        return float(similarity)

# Global instance
_embedding_service = None

def get_embedding_service() -> MiniLMEmbeddingService:
    """Get or create embedding service singleton"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = MiniLMEmbeddingService()
    return _embedding_service