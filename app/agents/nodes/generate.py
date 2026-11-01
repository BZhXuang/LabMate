"""Answer generation and refusal nodes."""

from __future__ import annotations

import json
import time

from pydantic import BaseModel, Field

from app.agents.state import AgentState
from app.core.enums import IntentLabel, RetrievalStrategy
from app.core.exceptions import LLMOutputError, LLMProviderError
from app.memory.context import context_text
from app.prompts.answer import ANSWER_SYSTEM, ANSWER_USER
from app.providers.base import LLMProvider
from app.providers.fake import OfflineLLMProvider
from app.providers.json_parser import parse_model
from app.schemas.agent import ToolResult
from app.schemas.common import LatencyBreakdown, TokenUsage
from app.schemas.retrieval import Citation


class AnswerPayload(BaseModel):
    answer: str
    citation_chunk_ids: list[str] = Field(default_factory=list)
    refused: bool = False


async def generate_node(state: AgentState, llm: LLMProvider) -> dict:
    started = time.perf_counter()
    intent = state.get("intent")
    if intent and intent.label == IntentLabel.HUMAN_HANDOFF:
        return {
            "final_answer": "请通过本校实验平台公示的联系方式联系设备管理员或实验室安全员。本演示系统没有真实人工转接或通知功能。",
            "citations": [],
            "refused": False,
        }
    chunks = state.get("retrieved_chunks") or []
    tools = state.get("tool_results") or []
    if tools and all(not tool.success for tool in tools):
        return {
            "final_answer": "暂时无法完成本次查询或申请，请核对设备编号、时段及业务条件后重试。",
            "citations": [],
        }
    pending = state.get("pending_action")
    if pending:
        answer = pending.summary
        latency = state.get("latency") or LatencyBreakdown()
        latency.llm_ms = (time.perf_counter() - started) * 1000
        return {
            "final_answer": answer,
            "citations": [],
            "refused": False,
            "latency": latency,
        }
    missing_fields = (state.get("extra") or {}).get("missing_action_fields") or []
    if missing_fields:
        labels = {
            "equipment_id": "设备编号",
            "start_at": "预约开始时间（含时区）",
            "end_at": "预约结束时间（含时区）",
            "purpose": "使用用途",
            "issue": "具体故障现象",
        }
        needed = "、".join(labels.get(str(field), str(field)) for field in missing_fields)
        return {
            "final_answer": f"提交前还需要补充：{needed}。补充后我会先展示待确认申请。",
            "citations": [],
        }
    evidence = (
        "\n\n".join(f"[{c.chunk_id}] {c.title}\n{c.content}" for c in chunks[:6]) or "(无检索结果)"
    )
    tool_text = json.dumps([t.model_dump() for t in tools], ensure_ascii=False) if tools else "(无)"
    intent = state.get("intent")
    strategy = state.get("strategy") or RetrievalStrategy.DIRECT
    if isinstance(llm, OfflineLLMProvider):
        answer, citation_ids = _offline_answer(state)
        citations = [
            Citation(
                document_id=chunk.document_id,
                title=chunk.title,
                chunk_id=chunk.chunk_id,
                section=chunk.section,
            )
            for chunk in chunks
            if chunk.chunk_id in citation_ids
        ]
        citations.extend(
            citation for citation in _tool_citations(tools) if citation.chunk_id in citation_ids
        )
        return {"final_answer": answer, "citations": citations, "refused": False}
    messages = [
        {"role": "system", "content": ANSWER_SYSTEM},
        {
            "role": "user",
            "content": ANSWER_USER.format(
                query=state["user_query"],
                resolved_query=state.get("resolved_query") or state["user_query"],
                history=context_text(state),
                intent=intent.label.value if intent else "unknown",
                strategy=strategy.value,
                evidence=evidence,
                tool_results=tool_text,
            ),
        },
    ]
    try:
        response = await llm.generate(
            messages,
            temperature=0.2,
            max_tokens=700,
            response_format={"type": "json_object"},
        )
        payload = parse_model(response.content, AnswerPayload)
        usage = response.usage
    except (LLMProviderError, LLMOutputError):
        payload = AnswerPayload(
            answer=_extractive_fallback(state["user_query"], evidence, tool_text),
            citation_chunk_ids=[chunks[0].chunk_id] if chunks else [],
        )
        usage = TokenUsage()
    citations = [
        Citation(
            document_id=chunk.document_id,
            title=chunk.title,
            chunk_id=chunk.chunk_id,
            section=chunk.section,
        )
        for chunk in chunks
        if chunk.chunk_id in set(payload.citation_chunk_ids)
    ]
    cited_ids = set(payload.citation_chunk_ids)
    citations.extend(
        citation for citation in _tool_citations(tools) if citation.chunk_id in cited_ids
    )
    latency = state.get("latency") or LatencyBreakdown()
    latency.llm_ms = (time.perf_counter() - started) * 1000
    prev_usage = state.get("token_usage") or TokenUsage()
    merged = TokenUsage(
        prompt_tokens=prev_usage.prompt_tokens + usage.prompt_tokens,
        completion_tokens=prev_usage.completion_tokens + usage.completion_tokens,
        total_tokens=prev_usage.total_tokens + usage.total_tokens,
    )
    return {
        "final_answer": payload.answer,
        "citations": citations,
        "refused": payload.refused,
        "latency": latency,
        "token_usage": merged,
    }


async def refuse_node(state: AgentState) -> dict:
    return {
        "final_answer": "这个请求超出实验室设备运维助手的处理范围，或涉及绕过设备安全控制。我无法执行；请遵守本校实验室制度并联系设备管理员。",
        "refused": True,
        "citations": [],
    }


def _extractive_fallback(query: str, evidence: str, tool_text: str) -> str:
    if evidence and evidence != "(无检索结果)":
        snippet = evidence.split("\n", 1)[-1][:240].strip()
        return f"暂时无法生成完整答复。相关资料节选：\n\n> {snippet}\n\n请以原文为准。"
    if tool_text and tool_text != "(无)":
        return "已查询到系统数据，但暂时无法可靠地整理答复。请稍后重试或转人工。"
    return "暂时无法基于现有信息给出可靠答复，请补充相关信息或转人工。"


def _tool_citations(tools: list[ToolResult]) -> list[Citation]:
    citations: list[Citation] = []
    seen: set[str] = set()
    for result in tools:
        if not result.success or result.name != "search_knowledge":
            continue
        for item in result.output.get("chunks") or []:
            if not isinstance(item, dict) or not item.get("chunk_id"):
                continue
            chunk_id = str(item["chunk_id"])
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            citations.append(
                Citation(
                    document_id=str(item.get("document_id") or chunk_id.rsplit("_", 1)[0]),
                    title=str(item.get("title") or "知识库资料"),
                    chunk_id=chunk_id,
                    section=str(item["section"]) if item.get("section") else None,
                )
            )
    return citations


def _offline_answer(state: AgentState) -> tuple[str, set[str]]:
    """Use only retrieved text or whitelisted tool fields when no LLM is configured."""
    strategy = state.get("strategy")
    if strategy == RetrievalStrategy.DIRECT:
        return "你好，我是 LabMate，可以协助查询共享仪器资料、演示台账、预约时段和报修流程。", set()

    for result in reversed(state.get("tool_results") or []):
        if result.success and result.name == "search_knowledge":
            found = result.output.get("chunks") or []
            if found and isinstance(found[0], dict):
                item = found[0]
                title = str(item.get("title") or "实验室制度")
                excerpt = str(item.get("content") or "").strip()[:260]
                chunk_id = str(item.get("chunk_id") or "")
                citation_ids = {chunk_id} if chunk_id else set()
                return (
                    f"当前未配置生成模型。找到《{title}》中的资料节选，请核对来源和适用范围：\n\n> {excerpt}",
                    citation_ids,
                )

    for result in reversed(state.get("tool_results") or []):
        if not result.success:
            continue
        data = result.output
        if result.name == "get_lab_equipment_status":
            status = {
                "available": "台账标记为可申请",
                "in_use": "台账标记为使用中",
                "maintenance": "台账标记为维护中",
                "unavailable": "台账标记为暂不可用",
            }.get(str(data.get("status")), str(data.get("status", "未知")))
            return (
                f"演示台账中，{data.get('equipment_id', '')}（{data.get('name', '')}）位于{data.get('location', '未知位置')}，当前{status}。这不是实际学校的实时设备状态。",
                set(),
            )
        if result.name == "search_lab_equipment":
            equipment = data.get("equipment") or []
            if equipment:
                items = "；".join(
                    f"{item.get('equipment_id')} {item.get('name')}（{item.get('location')}，{item.get('status')}）"
                    for item in equipment[:5]
                )
                return f"演示台账查询结果：{items}。设备状态仅为本地演示数据。", set()
            return "演示台账中没有找到匹配设备。", set()
        if result.name == "check_lab_equipment_availability":
            bookings = data.get("bookings") or []
            if not bookings:
                return (
                    f"演示台账在 {data.get('date')} 暂无已登记申请或批准时段。{data.get('note', '')}",
                    set(),
                )
            windows = "；".join(
                f"{item.get('start_at')} 至 {item.get('end_at')}（{item.get('status')}）"
                for item in bookings
            )
            return f"演示台账查询到以下时段：{windows}。{data.get('note', '')}", set()
        if result.name == "request_lab_equipment_reservation":
            return (
                f"预约申请 {data.get('reservation_id')} 已登记为待审核。该记录来自演示数据库，不代表真实校园预约已获批准。",
                set(),
            )
        if result.name == "create_lab_maintenance_ticket":
            return (
                f"报修工单 {data.get('ticket_id')} 已登记，状态为待管理员处理。系统不会自动维修设备或通知真实学校。",
                set(),
            )
        if result.name == "search_knowledge":
            found = data.get("chunks") or []
            if found and isinstance(found[0], dict):
                item = found[0]
                title = str(item.get("title") or "相关政策")
                excerpt = str(item.get("content") or "").strip()[:260]
                return (
                    f"当前未配置生成模型。找到《{title}》中的资料节选，请核对原文：\n\n> {excerpt}",
                    set(),
                )

    chunks = state.get("retrieved_chunks") or []
    if chunks:
        chunk = chunks[0]
        excerpt = chunk.content.strip()[:260]
        return (
            f"当前未配置生成模型，以下是《{chunk.title}》的资料节选，请核对原文：\n\n> {excerpt}",
            {chunk.chunk_id},
        )
    return (
        "当前无法可靠回答这个问题。请补充相关信息，或联系人工客服。",
        set(),
    )
