import pytest

from app.agents.nodes.faithfulness import self_correct_answer
from app.guardrails.hallucination import FaithfulnessChecker
from app.providers.base import LLMResponse
from app.schemas.common import TokenUsage
from app.schemas.retrieval import RetrievedChunk


class _SequenceLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def ping(self) -> bool:
        return True

    async def generate(self, messages, **kwargs) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            content = '{"answer":"未培训也可以直接操作设备","citation_chunk_ids":[]}'
        else:
            content = '{"supported":true,"hallucinated_spans":[],"rationale":"ok"}'
        return LLMResponse(content=content, usage=TokenUsage(total_tokens=4), model="fake")


@pytest.mark.asyncio
async def test_self_correct_rewrites_unsupported_answer() -> None:
    llm = _SequenceLLM()
    checker = FaithfulnessChecker(llm)
    chunk = RetrievedChunk(
        chunk_id="c1",
        document_id="equipment_operation_0",
        title="设备操作",
        content="使用大型仪器前必须完成对应培训并取得操作授权。",
        score=1.0,
        rank=1,
        source="bm25",
    )
    from app.guardrails.hallucination import FaithfulnessResult

    first = FaithfulnessResult(
        supported=False, hallucinated_spans=["直接操作"], rationale="unsupported"
    )
    answer, judged, corrected = await self_correct_answer(
        llm=llm,
        checker=checker,
        query="没有培训可以直接使用设备吗？",
        answer="可以直接操作设备。",
        chunks=[chunk],
        tool_results_text="",
        first_result=first,
    )
    assert corrected is True
    assert judged.supported is True
    assert "培训" in answer
