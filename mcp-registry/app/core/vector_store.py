"""
VectorStore module for indexing and searching MCP tools.

This module provides vector search for MCP tools using
an OpenAI-compatible embeddings API (Mistral, OpenAI, etc.).
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple
import json
import requests
import numpy as np
from ..config.settings import EmbeddingConfig

logger = logging.getLogger(__name__)


class OpenAICompatibleEmbedder:
    """Client for an OpenAI-compatible embeddings API (Mistral, OpenAI, etc.)."""

    # Standard maximum dimension (OpenAI text-embedding-3-small)
    # Lower dimensions will be padded with zeros
    MAX_DIMENSION = 1536

    def __init__(self, api_url: str, api_key: str, model: str = "mistral-embed"):
        """
        Initialize the embedding client.

        Args:
            api_url: Base API URL (e.g., https://api.mistral.ai/v1)
            api_key: API key for authentication
            model: Embedding model to use (e.g., mistral-embed, text-embedding-3-small)
        """
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def _pad_embedding(self, embedding: List[float], target_dim: int = None) -> List[float]:
        """
        Pad an embedding with zeros to reach the target dimension.

        Args:
            embedding: The embedding to pad
            target_dim: Target dimension (default: MAX_DIMENSION)

        Returns:
            Embedding padded to target dimension
        """
        if target_dim is None:
            target_dim = self.MAX_DIMENSION

        current_dim = len(embedding)
        if current_dim >= target_dim:
            return embedding[:target_dim]  # Truncate if too large

        # Pad with zeros
        return embedding + [0.0] * (target_dim - current_dim)
    
    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for the provided texts via the API.
        Implements automatic batching to respect API limits.
        All embeddings are normalized to MAX_DIMENSION (1536) by padding.

        Args:
            texts: Texts to transform into embeddings

        Returns:
            Numpy array of embeddings (dimension: MAX_DIMENSION)
        """
        if not texts:
            return np.array([])

        try:
            # Build the embeddings URL (OpenAI/Mistral compatible)
            embeddings_url = f"{self.api_url}/embeddings" if "/v1" in self.api_url else f"{self.api_url}/v1/embeddings"

            # Standard batch limit
            BATCH_SIZE = 64
            all_embeddings = []

            # Process texts by batch
            for i in range(0, len(texts), BATCH_SIZE):
                batch = texts[i:i + BATCH_SIZE]
                batch_num = (i // BATCH_SIZE) + 1
                total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE

                logger.info(f"Processing batch {batch_num}/{total_batches}: {len(batch)} texts (total: {len(texts)})")

                payload = {"model": self.model, "input": batch}
                logger.debug(f"Calling embeddings API: URL={embeddings_url}, Model={self.model}")

                response = requests.post(
                    embeddings_url,
                    headers=self.headers,
                    json=payload
                )

                if response.status_code != 200:
                    logger.error(f"Embeddings API error (batch {batch_num}): {response.status_code} - {response.text}")
                    # Add empty embeddings of standard dimension for this batch
                    all_embeddings.extend([[0.0] * self.MAX_DIMENSION for _ in range(len(batch))])
                    continue

                result = response.json()

                # Extract embeddings (standard OpenAI/Mistral format)
                batch_embeddings = []
                for item in result.get("data", []):
                    embedding = item.get("embedding", [])
                    if embedding:
                        # Padding to MAX_DIMENSION for uniformity (Mistral=1024, OpenAI=1536)
                        padded = self._pad_embedding(embedding)
                        batch_embeddings.append(padded)

                if not batch_embeddings:
                    logger.warning(f"No embeddings received for batch {batch_num}")
                    # Add empty embeddings for this batch
                    all_embeddings.extend([[0.0] * self.MAX_DIMENSION for _ in range(len(batch))])
                else:
                    all_embeddings.extend(batch_embeddings)
                    # Log original dimension if different
                    orig_dim = len(result.get("data", [{}])[0].get("embedding", []))
                    if orig_dim and orig_dim != self.MAX_DIMENSION:
                        logger.info(f"Batch {batch_num}/{total_batches} OK: {len(batch_embeddings)} embeddings (dim {orig_dim} → {self.MAX_DIMENSION})")
                    else:
                        logger.info(f"Batch {batch_num}/{total_batches} OK: {len(batch_embeddings)} embeddings")

            if not all_embeddings:
                logger.warning("No embeddings received from API")
                return np.zeros((len(texts), self.MAX_DIMENSION))

            # Convert to numpy array - all elements have the same dimension thanks to padding
            return np.array(all_embeddings, dtype=np.float32)

        except Exception as e:
            logger.error(f"Exception during embedding generation: {str(e)}")
            return np.zeros((len(texts), self.MAX_DIMENSION))


class SimpleVectorStore:
    """
    Simplified vector store without FAISS.

    Uses simple cosine similarity comparison instead of FAISS to avoid
    compatibility issues.
    """

    def __init__(self):
        """Initialize the simplified vector store."""
        self.embeddings = []
        self.tool_ids = []

    def add(self, embeddings: np.ndarray, tool_ids: List[str]):
        """
        Add embeddings to the store.

        Args:
            embeddings: Embeddings to add
            tool_ids: IDs of the corresponding tools
        """
        self.embeddings = embeddings
        self.tool_ids = tool_ids

    def search(self, query_embedding: np.ndarray, k: int = 5) -> List[Tuple[int, float]]:
        """
        Search for the closest embeddings.

        Args:
            query_embedding: Query embedding
            k: Number of results to return

        Returns:
            List of tuples (index, similarity score)
        """
        if len(self.embeddings) == 0:
            return []

        # Calculate cosine similarity
        dot_product = np.dot(self.embeddings, query_embedding.T).flatten()

        # Normalize to get cosine similarity
        query_norm = np.linalg.norm(query_embedding)
        corpus_norm = np.linalg.norm(self.embeddings, axis=1)
        cosine_similarities = dot_product / (query_norm * corpus_norm)

        # Get sorted indices
        sorted_indices = np.argsort(cosine_similarities)[::-1]

        # Return the top k results
        results = []
        for i in range(min(k, len(sorted_indices))):
            idx = sorted_indices[i]
            score = float(cosine_similarities[idx])
            results.append((idx, score))

        return results


class VectorStore:
    """
    Vector store for MCP tools using OpenAI-compatible embedding API.

    This class handles embedding and indexing of tool descriptions
    to enable semantic search. Compatible with Mistral, OpenAI, etc.
    """

    def __init__(self, config: EmbeddingConfig):
        """
        Initialize the vector store with the given configuration.

        Args:
            config: Configuration for the embedding model and vector store
        """
        self.config = config
        self.index = SimpleVectorStore()
        self.tool_ids = []

        # Get API configuration from environment variables
        # Priority: EMBEDDING_API_URL > LLM_API_URL > Mistral default
        self.api_url = os.environ.get(
            "EMBEDDING_API_URL",
            os.environ.get("LLM_API_URL", "https://api.mistral.ai/v1")
        )
        self.api_key = os.environ.get(
            "EMBEDDING_API_KEY",
            os.environ.get("LLM_API_KEY", "")
        )

        if not self.api_key:
            logger.warning(
                "No API key configured for embeddings. "
                "Set EMBEDDING_API_KEY or LLM_API_KEY to enable semantic search."
            )

        # Embedding model (default: mistral-embed for Mistral API)
        default_model = "mistral-embed" if "mistral" in self.api_url.lower() else "text-embedding-3-small"
        self.embedding_model_name = os.environ.get("EMBEDDING_MODEL", default_model)

        # Initialize the embedding client
        self.embedding_model = OpenAICompatibleEmbedder(
            api_url=self.api_url,
            api_key=self.api_key,
            model=self.embedding_model_name
        )
    
    def build_index(self, tools: List[Dict[str, Any]]) -> None:
        """
        Build an index from the provided tools.

        Args:
            tools: List of tool dictionaries with metadata
        """
        if not tools:
            logger.warning("No tools provided for indexing")
            self.index = SimpleVectorStore()
            self.tool_ids = []
            return

        try:
            # Extract tool IDs and generate rich text for embedding
            self.tool_ids = []
            texts = []

            for tool in tools:
                tool_id = tool.get("id")
                if not tool_id:
                    continue

                self.tool_ids.append(tool_id)

                # Create a rich textual representation for embedding
                text = f"{tool.get('name', '')} - {tool.get('description', '')}"

                # Add parameter information if available
                params = tool.get("parameters", {})
                if params and isinstance(params, dict) and "properties" in params:
                    param_properties = params.get("properties", {})
                    param_text = " ".join([
                        f"{name}: {prop.get('description', '')}"
                        for name, prop in param_properties.items()
                    ])
                    text += f" Parameters: {param_text}"

                texts.append(text)

            if not texts:
                logger.warning("No valid tools for indexing")
                self.index = SimpleVectorStore()
                return

            # Generate embeddings via the configured API
            embeddings = self.get_embeddings(texts)

            # Create the simplified index
            self.index = SimpleVectorStore()
            self.index.add(embeddings, self.tool_ids)

            logger.info(f"Index built with {len(self.tool_ids)} tools")
        except Exception as e:
            logger.error(f"Failed to build index: {str(e)}")
            self.index = SimpleVectorStore()
            self.tool_ids = []
    
    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for the provided texts.

        Args:
            texts: List of texts to transform into embeddings

        Returns:
            Numpy array of embeddings (dimension: MAX_DIMENSION=1536)
        """
        if not self.embedding_model:
            logger.error("Embedding model not initialized")
            # Return an empty embedding of standard dimension (1536 = MAX_DIMENSION)
            return np.zeros((len(texts), OpenAICompatibleEmbedder.MAX_DIMENSION))

        return self.embedding_model.get_embeddings(texts)
    
    def search(self, query: str, k: int = 5, limit: Optional[int] = None) -> List[str]:
        """
        Search for tools similar to the query.

        Args:
            query: The search query
            k: Number of results to return (deprecated, use limit)
            limit: Number of results to return

        Returns:
            List of similar tool IDs
        """
        # Use limit if provided, otherwise use k
        result_count = limit if limit is not None else k

        if not self.index or not self.tool_ids:
            logger.warning("Index not built or empty, unable to perform search")
            return []

        try:
            # Get the query embedding
            query_embedding = self.get_embeddings([query])

            # Search in the index
            result_count = min(result_count, len(self.tool_ids))
            results = self.index.search(query_embedding, result_count)

            # Format the results
            formatted_results = []
            for idx, score in results:
                if idx < 0 or idx >= len(self.tool_ids):
                    continue

                tool_id = self.tool_ids[idx]
                formatted_results.append(tool_id)

            return formatted_results
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            return []

    def search_with_scores(self, query: str, k: int = 5, threshold: float = 0.0) -> List[Tuple[str, float]]:
        """
        Search for similar items and return results with similarity scores.

        Args:
            query: The search query
            k: Maximum number of results
            threshold: Minimum similarity score (0.0 to 1.0) to include in results

        Returns:
            List of tuples (tool_id, similarity_score) sorted by score descending
        """
        if not self.index or not self.tool_ids:
            logger.warning("Index not built or empty")
            return []

        try:
            # Get query embedding
            query_embedding = self.get_embeddings([query])

            # Search in index
            result_count = min(k, len(self.tool_ids))
            results = self.index.search(query_embedding, result_count)

            # Format results with scores, filtering by threshold
            formatted_results = []
            for idx, score in results:
                if idx < 0 or idx >= len(self.tool_ids):
                    continue
                if score < threshold:
                    continue

                tool_id = self.tool_ids[idx]
                formatted_results.append((tool_id, score))

            return formatted_results
        except Exception as e:
            logger.error(f"Search with scores failed: {str(e)}")
            return []

    def find_similar(self, text: str, k: int = 10, threshold: float = 0.75) -> List[Tuple[str, float]]:
        """
        Find items semantically similar to the given text.

        This is useful for deduplication - finding servers that might be
        duplicates based on semantic similarity of their descriptions.

        Args:
            text: Text to find similar items for (e.g., server name + description)
            k: Maximum number of results
            threshold: Minimum similarity score (default 0.75 for duplicates)

        Returns:
            List of tuples (item_id, similarity_score) with score >= threshold
        """
        return self.search_with_scores(text, k=k, threshold=threshold) 