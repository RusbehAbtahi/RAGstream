"""
Embedder
========
Wraps OpenAI embeddings API to convert text chunks into dense vectors.
"""
from typing import List
import os
from dotenv import load_dotenv
from openai import OpenAI

class Embedder:
    """High-level embedding interface using OpenAI API."""
    def __init__(self, model: str = "text-embedding-3-large"):
        load_dotenv()  # Load .env file
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment or .env file")

        self.client = OpenAI(api_key=api_key)
        self.model = model

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        Returns: list of embedding vectors (one per text)
        """
        if not texts:
            return []

        # OpenAI API allows batch embedding calls
        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )

        # Extract embeddings from response
        embeddings = [item.embedding for item in response.data]
        return embeddings
