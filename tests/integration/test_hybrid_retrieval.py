import pytest

from app.config.settings import clear_settings_cache, get_settings
from app.providers.embeddings import HashEmbeddingProvider
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.ingest import ingest_to_memory
from app.retrieval.vector import VectorRetriever


@pytest.mark.asyncio
async def test_hybrid_retrieves_lab_booking_guidance() -> None:
    clear_settings_cache()
    embedder = HashEmbeddingProvider(dim=get_settings().embedding_dim)
    bm25, store, chunks = await ingest_to_memory("knowledge/labops", embedder)
    assert chunks
    retriever = HybridRetriever(bm25, VectorRetriever(store, embedder), rrf_k=60)
    hits = await retriever.retrieve("预约大型共享仪器前需要完成什么培训", top_k=5)
    assert hits
    blob = " ".join(hit.content for hit in hits)
    assert "培训" in blob or "预约" in blob
