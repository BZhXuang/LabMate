"""Intent and complexity routing nodes."""

from __future__ import annotations

import time

from app.agents.nodes.intent import IntentClassifier
from app.agents.state import AgentState
from app.core.enums import IntentLabel, QueryComplexity, RetrievalStrategy
from app.memory.context import is_conversation_only
from app.retrieval.adaptive import AdaptiveRouter
from app.schemas.agent import ComplexityResult, IntentResult
from app.schemas.common import LatencyBreakdown


def _latency(state: AgentState) -> LatencyBreakdown:
    return state.get("latency") or LatencyBreakdown()


async def intent_node(state: AgentState, classifier: IntentClassifier) -> dict:
    started = time.perf_counter()
    intent = (
        IntentResult(
            label=IntentLabel.FAQ_POLICY,
            confidence=1.0,
            rationale="user_conversation_background",
            prompt_version="context_v1",
        )
        if is_conversation_only(state["user_query"])
        else await classifier.classify(state.get("resolved_query") or state["user_query"])
    )
    latency = _latency(state)
    latency.intent_ms = (time.perf_counter() - started) * 1000
    return {"intent": intent, "latency": latency}


async def router_node(state: AgentState, router: AdaptiveRouter) -> dict:
    started = time.perf_counter()
    intent = state["intent"]
    assert intent is not None
    complexity = (
        ComplexityResult(
            complexity=QueryComplexity.TOOL_REQUIRED,
            strategy=RetrievalStrategy.AGENT,
            confidence=1.0,
            rationale="confirmed_action",
        )
        if state.get("confirmed_action")
        else ComplexityResult(
            complexity=QueryComplexity.SIMPLE,
            strategy=RetrievalStrategy.DIRECT,
            confidence=1.0,
            rationale="conversation_or_handoff",
        )
        if is_conversation_only(state["user_query"]) or intent.label == IntentLabel.HUMAN_HANDOFF
        else await router.route(state.get("resolved_query") or state["user_query"], intent)
    )
    latency = _latency(state)
    latency.routing_ms = (time.perf_counter() - started) * 1000
    return {
        "complexity": complexity,
        "strategy": complexity.strategy,
        "query_complexity": complexity.complexity,
        "latency": latency,
    }
