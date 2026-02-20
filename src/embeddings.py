"""
Azure OpenAI embedding client for generating text embeddings.
"""
import os
import time
from typing import List

# Make openai import resilient
OPENAI_AVAILABLE = True
OPENAI_IMPORT_ERROR = None
try:
    from openai import AzureOpenAI
except Exception as e:
    OPENAI_AVAILABLE = False
    OPENAI_IMPORT_ERROR = e


class EmbeddingClient:
    """Client for generating embeddings using Azure OpenAI."""
    
    def __init__(self, endpoint: str, deployment_name: str, api_version: str, api_key: str = None):
        """
        Initialize the Azure OpenAI embedding client.
        
        Args:
            endpoint: Azure OpenAI endpoint URL
            deployment_name: Name of the deployed embedding model
            api_version: API version to use
            api_key: API key (if None, reads from AZURE_OPENAI_API_KEY env var)
        """
        if not OPENAI_AVAILABLE:
            raise RuntimeError(f"OpenAI SDK is not available: {OPENAI_IMPORT_ERROR}")
        
        self.deployment_name = deployment_name
        self.api_key = api_key or os.environ.get('AZURE_OPENAI_API_KEY')
        
        if not self.api_key:
            raise ValueError(
                "Azure OpenAI API key not found. "
                "Set AZURE_OPENAI_API_KEY environment variable or pass api_key parameter."
            )
        
        self.client = AzureOpenAI(
            api_key=self.api_key,
            api_version=api_version,
            azure_endpoint=endpoint
        )
        
        # Azure OpenAI embedding API limits
        self.max_batch_size = 16
        self.max_retries = 3
        self.initial_retry_delay = 1.0
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Handles batching and rate limiting automatically.
        
        Args:
            texts: List of text strings to embed
        
        Returns:
            List of embedding vectors (each is a list of floats)
        """
        if not texts:
            return []
        
        all_embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), self.max_batch_size):
            batch = texts[i:i + self.max_batch_size]
            batch_embeddings = self._embed_batch_with_retry(batch)
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
    
    def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a single query text.
        
        Args:
            query: Query text to embed
        
        Returns:
            Embedding vector as list of floats
        """
        embeddings = self.embed_texts([query])
        return embeddings[0] if embeddings else []
    
    def _embed_batch_with_retry(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of texts with exponential backoff retry logic.
        
        Args:
            texts: Batch of texts to embed (max self.max_batch_size)
        
        Returns:
            List of embedding vectors
        """
        retry_delay = self.initial_retry_delay
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.embeddings.create(
                    input=texts,
                    model=self.deployment_name
                )
                
                # Extract embeddings in the correct order
                embeddings = [item.embedding for item in response.data]
                return embeddings
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if it's a rate limit error
                if 'rate' in error_str or 'quota' in error_str or '429' in error_str:
                    if attempt < self.max_retries - 1:
                        print(f"Rate limit hit, retrying in {retry_delay}s... (attempt {attempt + 1}/{self.max_retries})")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                
                # Non-retryable error or final attempt
                print(f"Error generating embeddings: {e}")
                raise
        
        raise RuntimeError(f"Failed to generate embeddings after {self.max_retries} attempts")
