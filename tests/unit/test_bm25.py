from app.core.enums import DocumentCategory
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.chunking import chunk_markdown, stable_chunk_id


def test_chunk_ids_are_stable() -> None:
    text = "## 预约\n\n预约申请需完整填写设备编号。\n\n## 故障\n\n设备出现异常时联系管理员。"
    once = chunk_markdown(
        text,
        document_id="booking_guide",
        title="预约指南",
        category=DocumentCategory.LAB_OPERATIONS,
        source="x",
    )
    twice = chunk_markdown(
        text,
        document_id="booking_guide",
        title="预约指南",
        category=DocumentCategory.LAB_OPERATIONS,
        source="x",
    )
    assert [c.chunk_id for c in once] == [c.chunk_id for c in twice]
    assert once[0].chunk_id == stable_chunk_id("booking_guide", 0)


def test_bm25_ranks_lexical_match() -> None:
    chunks = chunk_markdown(
        "## 预约申请\n\n申请前需完成对应设备培训并填写设备编号。",
        document_id="doc",
        title="policy",
        category=DocumentCategory.LAB_OPERATIONS,
        source="x",
    )
    retriever = BM25Retriever(chunks)
    hits = retriever.search("预约申请 设备培训", top_k=2)
    assert hits
    assert "预约" in hits[0].content or "培训" in hits[0].content
