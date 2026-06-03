"""
Retrieval Orchestration Module - Retrieval service
Orchestrates the main retrieval workflow across vector store and structured data
"""

import logging
from typing import Optional, Dict, Any, List
import asyncio

logger = logging.getLogger(__name__)


class RetrievalOrchestrator:
    """
    Orchestrates the retrieval workflow.
    
    Workflow:
    1. Process query (query processor)
    2. Embed query (embedding client)
    3. Search vector store (vector store client)
    4. Retrieve structured data (repositories)
    5. Rank and filter results (ranker)
    6. Return results
    """
    
    def __init__(
        self,
        vector_store_client=None,
        embedding_client=None,
        document_repository=None,
        ranker=None
    ):
        """
        Initialize retrieval orchestrator.
        
        Args:
            vector_store_client: Qdrant/vector store client
            embedding_client: Embedding service client
            document_repository: Document data access layer
            ranker: Result ranking logic
        """
        self.vector_store = vector_store_client
        self.embeddings = embedding_client
        self.repository = document_repository
        self.ranker = ranker
    
    async def retrieve_semantic(
        self,
        query: str,
        top_k: int = 10,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve documents via semantic search.
        
        Args:
            query: Query text
            top_k: Number of results to return
            
        Returns:
            List of documents with similarity scores
        """
        active_collection = collection_name or (self.vector_store.collection_name if self.vector_store else "N/A")
        logger.info(f"Semantic search for: {query[:100]}... (collection: {active_collection})")
        
        try:
            if not self.embeddings:
                logger.error("Embedding client not configured")
                return []
            
            if not self.vector_store:
                logger.error("Vector store client not configured")
                return []
            
            logger.debug(f"Vector store collection: {active_collection}")
            logger.debug(f"Vector store client: {self.vector_store.client}")
            
            # Embed query
            logger.debug(f"Embedding query: {query[:100]}...")
            embedding = await self.embeddings.embed_query(query)
            
            # Validate embedding
            if not embedding or len(embedding) == 0:
                logger.warning(f"Invalid embedding generated for query: {query[:50]}...")
                return []
            
            logger.debug(f"Embedding generated successfully (dimension: {len(embedding)})")
            
            # Search vector store
            logger.debug(f"Searching vector store collection '{active_collection}' with top_k={top_k}")
            results = await self.vector_store.search(
                embedding=embedding,
                top_k=top_k,
                collection_name=collection_name,
            )
            
            logger.info(f"Found {len(results)} documents from semantic search (collection: {active_collection})")
            return results
            
            
        except Exception as e:
            logger.error(f"Semantic search error: {e}")
            return []
    
    async def retrieve_structured(
        self,
        query: str,
        query_tokens: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Retrieve structured data via keyword matching and database queries.
        
        Args:
            query: Query text
            query_tokens: Extracted tokens
            
        Returns:
            List of structured data results
        """
        logger.info(f"Structured search with tokens: {query_tokens}")
        
        try:
            if not self.repository:
                return []
            
            # Search repository by tokens
            results = await self.repository.search_by_keywords(query_tokens)
            
            logger.info(f"Found {len(results)} structured results")
            return results
            
        except Exception as e:
            logger.error(f"Structured search error: {e}")
            return []
    
    async def retrieve(
        self,
        processed_query: Any,
        top_k: int = 10,
        use_semantic: bool = True,
        use_structured: bool = True,
        collection_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Perform complete retrieval workflow.
        
        Args:
            processed_query: ProcessedQuery object
            top_k: Number of results
            use_semantic: Include semantic search
            use_structured: Include structured search
            
        Returns:
            Aggregated results from all sources
        """
        logger.info(f"Starting retrieval for: {processed_query.original}")
        
        try:
            # Parallel search if both enabled
            if use_semantic and use_structured:
                semantic_task = self.retrieve_semantic(
                    processed_query.expanded,
                    top_k,
                    collection_name=collection_name,
                )
                structured_task = self.retrieve_structured(
                    processed_query.normalized,
                    processed_query.tokens
                )
                
                semantic_results, structured_results = await asyncio.gather(
                    semantic_task,
                    structured_task,
                    return_exceptions=True
                )

                if isinstance(semantic_results, Exception):
                    logger.error(f"Semantic retrieval task failed: {semantic_results}")
                    semantic_results = []
                if isinstance(structured_results, Exception):
                    logger.error(f"Structured retrieval task failed: {structured_results}")
                    structured_results = []

                semantic_results = semantic_results or []
                structured_results = structured_results or []
            else:
                semantic_results = []
                structured_results = []
                
                if use_semantic:
                    semantic_results = await self.retrieve_semantic(
                        processed_query.expanded,
                        top_k,
                        collection_name=collection_name,
                    )
                
                if use_structured:
                    structured_results = await self.retrieve_structured(
                        processed_query.normalized,
                        processed_query.tokens
                    )
            
            # Aggregate results
            all_results = semantic_results + structured_results
            
            # Rank if ranker available
            if self.ranker:
                all_results = self.ranker.rank(
                    all_results,
                    processed_query.normalized
                )
            
            # Remove duplicates
            seen = set()
            deduped = []
            for result in all_results:
                doc_id = result.get("doc_id") or result.get("id")
                if doc_id not in seen:
                    seen.add(doc_id)
                    deduped.append(result)
            
            return {
                "query": processed_query.original,
                "documents": deduped[:top_k],
                "total_count": len(deduped),
                "semantic_count": len(semantic_results),
                "structured_count": len(structured_results),
            }
            
        except Exception as e:
            logger.error(f"Retrieval error: {e}")
            return {
                "query": processed_query.original,
                "documents": [],
                "error": str(e),
            }
