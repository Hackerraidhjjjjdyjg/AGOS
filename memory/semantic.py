"""
AGOS — Semantic Memory
ChromaDB vector store for semantic knowledge and RAG retrieval.
"""

import logging
from typing import Optional

logger = logging.getLogger("agos.memory.semantic")

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    logger.warning("ChromaDB not installed. Semantic memory disabled.")


class SemanticMemory:
    """
    Vector-based semantic memory using ChromaDB.
    Stores facts, documents, and knowledge with embedding-based retrieval.
    """

    def __init__(self, persist_dir: str = "./data/semantic_memory"):
        if not HAS_CHROMADB:
            self.client = None
            self.collection = None
            return

        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name="agos_knowledge",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"SemanticMemory initialized: {self.collection.count()} documents")

    def store(self, doc_id: str, text: str, metadata: Optional[dict] = None) -> None:
        """Store a fact or document with its embedding."""
        if self.collection is None:
            return
        self.collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata or {}],
        )
        logger.debug(f"Stored: {doc_id}")

    def recall(self, query: str, n_results: int = 5) -> list[dict]:
        """Retrieve the most relevant documents for a query."""
        if self.collection is None:
            return []
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
        )
        docs = []
        for i in range(len(results["ids"][0])):
            docs.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "distance": results["distances"][0][i] if results.get("distances") else None,
                "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
            })
        return docs

    def count(self) -> int:
        """Get total number of stored documents."""
        if self.collection is None:
            return 0
        return self.collection.count()
