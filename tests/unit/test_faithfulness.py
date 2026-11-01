import pytest

from app.agents.nodes.faithfulness import faithfulness_node
from app.core.enums import RetrievalStrategy
from app.guardrails.hallucination import FaithfulnessResult
from app.providers.fake import FakeLLMProvider
from app.schemas.retrieval import RetrievedChunk


class _UnavailableChecker:
    async def check(self, **kwargs) -> FaithfulnessResult:
        return FaithfulnessResult(supported=False, rationale="checker_unavailable")


@pytest.mark.asyncio
async def test_unavailable_checker_returns_cited_excerpt_without_claiming_model_missing() -> None:
    chunk = RetrievedChunk(
        chunk_id="booking_chunk_1",
        document_id="shared_instrument_booking",
        title="共享仪器预约办法",
        content="预约前应核实设备是否要求培训或管理员授权。",
        score=1.0,
        rank=1,
        source="bm25",
    )
    state = {
        "user_query": "预约前需要完成培训吗？",
        "final_answer": "待核验的生成式回答。",
        "retrieved_chunks": [chunk],
        "tool_results": [],
        "strategy": RetrievalStrategy.SINGLE,
    }

    result = await faithfulness_node(state, _UnavailableChecker(), FakeLLMProvider())

    assert "预约前应核实设备是否要求培训" in result["final_answer"]
    assert "未配置生成模型" not in result["final_answer"]
    assert result["citations"][0].title == "共享仪器预约办法"
