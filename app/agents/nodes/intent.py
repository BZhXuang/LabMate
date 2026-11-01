"""Intent classification: rule fast path plus LLM classifier."""

from __future__ import annotations

import re

from app.agents.nodes.intent_overlay import apply_intent_overlay, high_precision_intent
from app.core.constants import PROMPT_VERSION_INTENT
from app.core.enums import IntentLabel
from app.core.exceptions import LLMOutputError, LLMProviderError
from app.prompts.intent import INTENT_SYSTEM, INTENT_USER
from app.providers.base import LLMProvider
from app.providers.fake import OfflineLLMProvider
from app.providers.json_parser import parse_model
from app.schemas.agent import IntentResult

_GREETING = re.compile(r"(?:你好|您好|hi|hello|早上好)[!！。．.\s]*", re.IGNORECASE)


def rule_based_intent(query: str) -> IntentResult:
    lab_label = high_precision_intent(query)
    if lab_label == IntentLabel.OUT_OF_SCOPE:
        return IntentResult(
            label=IntentLabel.OUT_OF_SCOPE,
            confidence=0.92,
            rationale="safety_or_scope_boundary",
            prompt_version="intent_rules_v1",
        )
    if lab_label in {
        IntentLabel.GREETING,
        IntentLabel.CHITCHAT,
        IntentLabel.HUMAN_HANDOFF,
        IntentLabel.LAB_EQUIPMENT,
        IntentLabel.LAB_BOOKING,
        IntentLabel.LAB_MAINTENANCE,
        IntentLabel.LAB_SAFETY,
    }:
        return IntentResult(
            label=lab_label,
            confidence=0.88,
            rationale="high_precision_overlay",
            prompt_version="intent_rules_v1",
        )
    if _GREETING.fullmatch(query.strip()):
        return IntentResult(
            label=IntentLabel.GREETING,
            confidence=0.9,
            rationale="greeting_rule",
            prompt_version="intent_rules_v1",
        )
    if any(word in query.lower() for word in ("ignore previous", "jailbreak", "系统提示词")) or any(
        word in query for word in ("总统", "选谁", "怎么造炸弹", "炒股", "医疗诊断")
    ):
        return IntentResult(
            label=IntentLabel.OUT_OF_SCOPE,
            confidence=0.9,
            rationale="blocked_topic",
            prompt_version="intent_rules_v1",
        )
    return IntentResult(
        label=IntentLabel.FAQ_POLICY,
        confidence=0.55,
        rationale="default_faq",
        prompt_version="intent_rules_v1",
    )


class IntentClassifier:
    def __init__(
        self,
        llm: LLMProvider,
        *,
        system_prompt: str = INTENT_SYSTEM,
        prompt_version: str = PROMPT_VERSION_INTENT,
        apply_overlay: bool = True,
    ) -> None:
        self._llm = llm
        self._system_prompt = system_prompt
        self._prompt_version = prompt_version
        self._apply_overlay = apply_overlay

    async def classify(self, query: str) -> IntentResult:
        fallback = rule_based_intent(query)
        if isinstance(self._llm, OfflineLLMProvider):
            return self._maybe_overlay(query, fallback)
        try:
            response = await self._llm.generate(
                [
                    {"role": "system", "content": self._system_prompt},
                    {
                        "role": "user",
                        "content": INTENT_USER.format(
                            query=query, prompt_version=self._prompt_version
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=256,
                response_format={"type": "json_object"},
            )
            parsed = parse_model(response.content, IntentResult)
            if not parsed.prompt_version:
                parsed.prompt_version = self._prompt_version
            return self._maybe_overlay(query, parsed)
        except (LLMProviderError, LLMOutputError):
            return self._maybe_overlay(query, fallback)

    def _maybe_overlay(self, query: str, parsed: IntentResult) -> IntentResult:
        if not self._apply_overlay:
            return parsed
        label, overlay_note = apply_intent_overlay(query, parsed.label)
        if overlay_note:
            parsed.label = label
            parsed.rationale = f"{parsed.rationale};{overlay_note}"
            parsed.confidence = max(parsed.confidence, 0.93)
        return parsed
