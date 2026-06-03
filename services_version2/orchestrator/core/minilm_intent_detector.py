"""
MiniLM-Based Intent Detection - Fast Semantic Classification
============================================================================

Uses all-MiniLM-L12-v2 embeddings for semantic intent classification.
Layer 1 (Primary) for two-layer intent detection system.

Features:
  - Fast inference (<100ms per query)
  - No GPU required
  - Semantic understanding without LLM API calls
  - Confidence scoring based on embedding similarity
  - Thread-safe singleton pattern
"""

import logging
import numpy as np
from typing import Optional, Tuple, Union
from enum import Enum
import os

logger = logging.getLogger(__name__)


class MiniLMIntentDetector:
    """
    Intent detection using all-MiniLM-L12-v2 embeddings.
    Provides semantic understanding for Layer 1 intent classification.
    
    Intent patterns are pre-defined as text strings. Questions and patterns
    are encoded to embeddings, then cosine similarity is computed.
    """
    
    # Define intent patterns as representative text samples
    INTENT_PATTERNS = {
        "calculation": [
            "Calculate the import duty and tax",
            "How much will I pay in customs tax",
            "What is the total tariff cost",
            "Compute the duty for HS code",
        ],
        "hs_code_lookup": [
            "What is the HS code for this product",
            "Classify this product with HS code",
            "Find the tariff code for goods",
            "Determine the harmonized code",
        ],
        "trade_query": [
            "What is the trade volume between countries",
            "Show me import export statistics",
            "Provide trade data and flows",
            "Trade route information",
        ],
        "definition": [
            "What does this term mean",
            "Explain this customs concept",
            "Provide background information",
            "Define these trade terms",
        ],
        "policy_query": [
            "What is the procedure for importing",
            "What regulations apply here",
            "What are the requirements",
            "Describe the process for customs clearance",
        ],
    }
    
    def __init__(self, embedding_model: Optional[str] = None):
        """
        Initialize MiniLM intent detector.
        
        Args:
            embedding_model: Model name (defaults to env var or 'all-MiniLM-L12-v2')
        """
        try:
            from .embedding_service import get_embedding_service
            self.embedding_service = get_embedding_service()
        except Exception as e:
            logger.warning(f"Could not import embedding_service: {e}. Using fallback.")
            self.embedding_service = None
        
        self.model_name = embedding_model or os.getenv(
            'INTENT_DETECTION_MODEL', 
            'all-MiniLM-L12-v2'
        )
        
        # Pre-compute pattern embeddings for faster matching
        self.pattern_embeddings = {}
        self._precompute_patterns()
        
        self.confidence_threshold = float(
            os.getenv('INTENT_CONFIDENCE_THRESHOLD', 0.75)
        )
        
        logger.info(f"✓ MiniLM Intent Detector initialized")
        logger.info(f"  Model: {self.model_name}")
        logger.info(f"  Confidence threshold: {self.confidence_threshold}")
        logger.info(f"  Pre-computed {len(self.pattern_embeddings)} intent patterns")
    
    def _precompute_patterns(self):
        """Pre-compute embeddings for all intent patterns."""
        if not self.embedding_service:
            logger.warning("Embedding service not available, skipping pattern precomputation")
            return
            
        try:
            for intent, patterns in self.INTENT_PATTERNS.items():
                pattern_texts = patterns
                embeddings = self.embedding_service.model.encode(
                    pattern_texts,
                    convert_to_tensor=False
                )
                # Store as numpy array for fast computation
                self.pattern_embeddings[intent] = embeddings
                logger.debug(f"Pre-computed {len(patterns)} patterns for {intent}")
        except Exception as e:
            logger.error(f"Failed to pre-compute patterns: {e}")
            # Continue without precomputation
    
    def detect(self, question: str) -> Tuple[str, float, str]:
        """
        Detect intent using semantic similarity between question and intent patterns.
        
        Algorithm:
          1. Encode question to embedding
          2. Compute cosine similarity to each intent's pattern embeddings
          3. Average similarities across patterns per intent
          4. Return intent with highest average similarity
          5. Compute confidence based on similarity score
        
        Args:
            question: User question
            
        Returns:
            (intent, confidence, reasoning)
            
        Raises:
            Exception: If embedding or similarity computation fails
        """
        if not self.embedding_service or not self.pattern_embeddings:
            logger.warning("[MiniLM] Embedding service not available, returning GENERAL")
            return "general", 0.5, "Embedding service unavailable"
            
        try:
            # Step 1: Encode question
            logger.debug(f"[MiniLM] Encoding question: {question[:60]}...")
            question_embedding = self.embedding_service.encode_query(question)
            
            # Step 2-4: Compute similarities and find best match
            best_intent = None
            best_similarity = -1.0
            intent_scores = {}
            
            try:
                from sentence_transformers.util import pytorch_cos_sim
                import torch
            except ImportError:
                # Fallback if torch not available
                logger.warning("[MiniLM] PyTorch/sentence_transformers not available, using numpy")
                return self._detect_with_numpy_fallback(question_embedding)
            
            for intent, pattern_embeddings in self.pattern_embeddings.items():
                # Convert question embedding to tensor for similarity
                q_tensor = torch.tensor([question_embedding])
                p_tensor = torch.tensor(pattern_embeddings)
                
                # Compute similarities
                similarities = pytorch_cos_sim(q_tensor, p_tensor)[0].tolist()
                avg_similarity = float(np.mean(similarities))
                intent_scores[intent] = avg_similarity
                
                logger.debug(
                    f"[MiniLM] {intent:15} → similarity: {avg_similarity:.3f} "
                    f"(samples: {len(similarities)})"
                )
                
                if avg_similarity > best_similarity:
                    best_similarity = avg_similarity
                    best_intent = intent
            
            # Step 5: Compute confidence
            confidence = best_similarity
            
            # Create reasoning string
            reasoning = (
                f"Semantic similarity: {best_intent} "
                f"(score: {best_similarity:.3f}, threshold: {self.confidence_threshold:.2f})"
            )
            
            logger.info(
                f"[MiniLM] Intent detected: {best_intent} "
                f"(confidence: {confidence:.3f})"
            )
            
            return best_intent, confidence, reasoning
            
        except Exception as e:
            logger.error(f"[MiniLM] Intent detection failed: {e}", exc_info=True)
            # Fallback to GENERAL intent on error
            return "general", 0.5, f"Error in MiniLM detection: {str(e)}"
    
    def _detect_with_numpy_fallback(self, question_embedding: np.ndarray) -> Tuple[str, float, str]:
        """Fallback intent detection using numpy cosine similarity."""
        best_intent = None
        best_similarity = -1.0
        
        for intent, pattern_embeddings in self.pattern_embeddings.items():
            # Compute cosine similarity manually with numpy
            similarities = []
            for pattern_emb in pattern_embeddings:
                similarity = np.dot(question_embedding, pattern_emb) / (
                    np.linalg.norm(question_embedding) * np.linalg.norm(pattern_emb) + 1e-10
                )
                similarities.append(similarity)
            
            avg_similarity = float(np.mean(similarities))
            
            if avg_similarity > best_similarity:
                best_similarity = avg_similarity
                best_intent = intent
        
        reasoning = f"Semantic similarity (numpy): {best_intent} (score: {best_similarity:.3f})"
        return best_intent, best_similarity, reasoning


# Global instance
_minilm_detector = None


def get_minilm_detector() -> MiniLMIntentDetector:
    """
    Get or create MiniLM intent detector singleton.
    
    Returns:
        MiniLMIntentDetector instance
    """
    global _minilm_detector
    if _minilm_detector is None:
        _minilm_detector = MiniLMIntentDetector()
    return _minilm_detector
