import pytest

from app.agents.nodes.generate import generate_node
from app.agents.nodes.intent import IntentClassifier, rule_based_intent
from app.core.enums import IntentLabel, RetrievalStrategy
from app.providers.fake import OfflineLLMProvider
from app.schemas.retrieval import RetrievedChunk


def test_greeting_prefix_does_not_hide_lab_maintenance_intent() -> None:
    intent = rule_based_intent("你好，我想报修 LAB-CF-01 的设备")
    assert intent.label == IntentLabel.LAB_MAINTENANCE


@pytest.mark.asyncio
async def test_offline_classifier_uses_rules_not_fake_json() -> None:
    intent = await IntentClassifier(OfflineLLMProvider()).classify("这个助手可以查询哪些实验室资料？")
    assert intent.label == IntentLabel.FAQ_POLICY


@pytest.mark.asyncio
async def test_offline_answer_quotes_evidence_instead_of_test_json() -> None:
    chunk = RetrievedChunk(
        chunk_id="chunk-1",
        document_id="policy-1",
        title="设备操作边界",
        content="使用大型仪器前须完成培训并取得操作授权；设备异常时应联系管理员。",
        score=1.0,
    )
    result = await generate_node(
        {
            "user_query": "设备异常时应该联系谁？",
            "strategy": RetrievalStrategy.MULTI,
            "retrieved_chunks": [chunk],
        },
        OfflineLLMProvider(),
    )
    assert "管理员" in result["final_answer"]
    assert "label" not in result["final_answer"]
    assert result["citations"][0].chunk_id == "chunk-1"
