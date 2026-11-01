"""Adaptive-RAG complexity routing.

Paper mapping (Jeong et al., ACL 2024):
- simple      -> DIRECT (no retrieval) or REFUSE
- single_hop  -> SINGLE (one-shot hybrid retrieval)
- multi_hop   -> MULTI  (Self-RAG iterative retrieval)
- tool needs  -> AGENT  (planner + tools, optional retrieval)

LLM classifier is preferred. Rule fallback keeps the system testable and
available when the model is down.
"""

from __future__ import annotations

import re

from app.core.constants import PROMPT_VERSION_COMPLEXITY
from app.core.enums import IntentLabel, QueryComplexity, RetrievalStrategy
from app.core.exceptions import LLMOutputError, LLMProviderError
from app.prompts.complexity import COMPLEXITY_SYSTEM, COMPLEXITY_USER
from app.providers.base import LLMProvider
from app.providers.fake import OfflineLLMProvider
from app.providers.json_parser import parse_model
from app.schemas.agent import ComplexityResult, IntentResult

_MULTI_HOP_CUES = (
    "同时",
    "并且",
    "还是",
    "如果",
    "但是已经",
    "过了",
    "既",
    "又",
    " besides",
    "and then",
)
_TOOL_CUES = (
    "设备状态",
    "仪器状态",
    "预约时段",
    "可用时段",
    "报修",
    "故障工单",
)
_LAB_EQUIPMENT_ID = re.compile(r"\bLAB-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", re.IGNORECASE)


def rule_based_complexity(query: str, intent: IntentResult) -> ComplexityResult:
    text = query.strip()
    if intent.label == IntentLabel.OUT_OF_SCOPE:
        return ComplexityResult(
            complexity=QueryComplexity.OUT_OF_SCOPE,
            strategy=RetrievalStrategy.REFUSE,
            confidence=0.95,
            rationale="intent_out_of_scope",
        )
    if intent.label in {IntentLabel.GREETING, IntentLabel.CHITCHAT}:
        return ComplexityResult(
            complexity=QueryComplexity.SIMPLE,
            strategy=RetrievalStrategy.DIRECT,
            confidence=0.9,
            rationale="social_or_greeting",
        )
    if intent.label in {IntentLabel.LAB_EQUIPMENT, IntentLabel.LAB_MAINTENANCE}:
        return ComplexityResult(
            complexity=QueryComplexity.TOOL_REQUIRED,
            strategy=RetrievalStrategy.AGENT,
            confidence=0.88,
            rationale="lab_equipment_tool_required",
        )
    if intent.label == IntentLabel.LAB_BOOKING:
        explicit_request = any(
            cue in text for cue in ("帮我预约", "提交预约", "申请预约", "替我预约")
        )
        if explicit_request or _LAB_EQUIPMENT_ID.search(text) or any(
            cue in text for cue in ("查一下空闲", "看下有没有空", "能预约吗")
        ):
            return ComplexityResult(
                complexity=QueryComplexity.TOOL_REQUIRED,
                strategy=RetrievalStrategy.AGENT,
                confidence=0.84,
                rationale="lab_booking_data_or_action",
            )
        return ComplexityResult(
            complexity=QueryComplexity.SINGLE_HOP,
            strategy=RetrievalStrategy.SINGLE,
            confidence=0.82,
            rationale="lab_booking_policy",
        )
    if intent.label == IntentLabel.LAB_SAFETY:
        hop_cues = sum(1 for cue in _MULTI_HOP_CUES if cue in text)
        multi = hop_cues > 0 and len(text) > 20
        return ComplexityResult(
            complexity=QueryComplexity.MULTI_HOP if multi else QueryComplexity.SINGLE_HOP,
            strategy=RetrievalStrategy.MULTI if multi else RetrievalStrategy.SINGLE,
            confidence=0.82,
            rationale="lab_safety_evidence_lookup",
        )
    if (
        _LAB_EQUIPMENT_ID.search(text)
        or any(cue in text.lower() for cue in _TOOL_CUES)
    ):
        return ComplexityResult(
            complexity=QueryComplexity.TOOL_REQUIRED,
            strategy=RetrievalStrategy.AGENT,
            confidence=0.8,
            rationale="entity_or_transactional_intent",
        )
    hop_cues = sum(1 for cue in _MULTI_HOP_CUES if cue in text)
    if hop_cues >= 1 and len(text) > 18:
        return ComplexityResult(
            complexity=QueryComplexity.MULTI_HOP,
            strategy=RetrievalStrategy.MULTI,
            confidence=0.7,
            rationale="multi_constraint_query",
        )
    return ComplexityResult(
        complexity=QueryComplexity.SINGLE_HOP,
        strategy=RetrievalStrategy.SINGLE,
        confidence=0.75,
        rationale="single_policy_or_faq",
    )


class AdaptiveRouter:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def route(self, query: str, intent: IntentResult) -> ComplexityResult:
        fallback = rule_based_complexity(query, intent)
        if isinstance(self._llm, OfflineLLMProvider):
            return fallback
        try:
            response = await self._llm.generate(
                [
                    {"role": "system", "content": COMPLEXITY_SYSTEM},
                    {
                        "role": "user",
                        "content": COMPLEXITY_USER.format(
                            query=query,
                            intent=intent.label.value,
                            prompt_version=PROMPT_VERSION_COMPLEXITY,
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=256,
                response_format={"type": "json_object"},
            )
            parsed = parse_model(response.content, ComplexityResult)
            if _LAB_EQUIPMENT_ID.search(query) and fallback.strategy == RetrievalStrategy.AGENT:
                return fallback
            return parsed
        except (LLMProviderError, LLMOutputError):
            return fallback
