"""Planner that turns intent, skills and complexity into tool plans."""

from __future__ import annotations

import re

from app.agents.state import AgentState
from app.core.exceptions import LLMOutputError, LLMProviderError
from app.core.ids import new_id
from app.memory.context import context_text
from app.prompts.planner import PLANNER_SYSTEM, PLANNER_USER
from app.providers.base import LLMProvider
from app.providers.fake import OfflineLLMProvider
from app.providers.json_parser import parse_model
from app.schemas.agent import AgentPlan, PlanStep
from app.schemas.chat import ActionProposal
from app.skills.loader import match_skill
from app.tools.permissions import WRITE_RISKS
from app.tools.registry import ToolRegistry

_EQUIPMENT_RE = re.compile(r"\bLAB-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", re.IGNORECASE)
_DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
_DATETIME_RE = re.compile(r"20\d{2}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})")
_ALWAYS_AVAILABLE = ("search_knowledge",)


class Planner:
    def __init__(self, llm: LLMProvider, registry: ToolRegistry) -> None:
        self._llm = llm
        self._registry = registry

    def _tool_catalog(self, allowed: set[str] | None = None) -> str:
        lines = []
        for tool in self._registry.all():
            if allowed is not None and tool.name not in allowed:
                continue
            lines.append(f"- {tool.name}: {tool.description} [{tool.risk.value}]")
        return "\n".join(lines) or "- (no tools)"

    async def create_plan(self, query: str, intent_label: str, summary: str) -> AgentPlan:
        skill = match_skill(query, intent_label)
        allowed = _allowed_tools(skill, self._registry)
        if isinstance(self._llm, OfflineLLMProvider):
            return (
                skill_to_plan(skill, query, self._registry)
                if skill
                else _knowledge_fallback(query, self._registry)
            )
        try:
            response = await self._llm.generate(
                [
                    {
                        "role": "system",
                        "content": PLANNER_SYSTEM.format(
                            tools=self._tool_catalog(allowed),
                            skill_context=_format_skill(skill),
                        ),
                    },
                    {
                        "role": "user",
                        "content": PLANNER_USER.format(
                            query=query, intent=intent_label, summary=summary or "无"
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=512,
                response_format={"type": "json_object"},
            )
            plan = parse_model(response.content, AgentPlan)
            plan = _sanitize_plan(plan, self._registry, allowed)
            if plan.steps:
                if skill:
                    plan.rationale = f"skill:{skill['name']};{plan.rationale}"
                return plan
        except (LLMOutputError, LLMProviderError):
            pass
        if skill:
            return skill_to_plan(skill, query, self._registry)
        return _knowledge_fallback(query, self._registry)


def _allowed_tools(skill: dict | None, registry: ToolRegistry) -> set[str] | None:
    if skill is None:
        return None
    names = set(registry.names())
    allowed = {name for name in skill.get("tools", []) if name in names}
    allowed.update(name for name in _ALWAYS_AVAILABLE if name in names)
    return allowed or None


def _format_skill(skill: dict | None) -> str:
    if skill is None:
        return "无（通用工具集）"
    steps = "、".join(skill.get("steps") or [])
    tools = ", ".join(skill.get("tools") or [])
    return f"{skill['name']}：{skill.get('description', '')}。步骤：{steps}。工具：{tools}"


def _sanitize_plan(
    plan: AgentPlan,
    registry: ToolRegistry,
    allowed: set[str] | None,
) -> AgentPlan:
    names = set(registry.names())
    if allowed is not None:
        names = names & allowed
    steps = [step for step in plan.steps if not step.tool_name or step.tool_name in names]
    return AgentPlan(steps=steps[:6], rationale=plan.rationale)


def skill_to_plan(skill: dict, query: str, registry: ToolRegistry) -> AgentPlan:
    steps: list[PlanStep] = []
    for index, tool_name in enumerate(skill.get("tools", []), start=1):
        if tool_name not in registry.names():
            continue
        steps.append(
            PlanStep(
                step_id=index,
                goal=skill["name"],
                tool_name=tool_name,
                arguments=_tool_arguments(tool_name, query),
                needs_retrieval=tool_name == "search_knowledge",
            )
        )
    if steps:
        return AgentPlan(steps=steps, rationale=f"skill:{skill['name']}")
    return _knowledge_fallback(query, registry)


def _tool_arguments(tool_name: str, query: str) -> dict:
    if tool_name in {"search_knowledge"}:
        return {"query": query[:200]}
    equipment_match = _EQUIPMENT_RE.search(query)
    equipment_id = equipment_match.group(0).upper() if equipment_match else None
    if tool_name == "search_lab_equipment":
        return {"query": query[:100]}
    if tool_name == "get_lab_equipment_status" and equipment_id:
        return {"equipment_id": equipment_id}
    if tool_name == "check_lab_equipment_availability":
        date_match = _DATE_RE.search(query)
        if equipment_id and date_match:
            return {"equipment_id": equipment_id, "date": date_match.group(0)}
    if tool_name == "request_lab_equipment_reservation":
        arguments: dict[str, object] = {}
        if equipment_id:
            arguments["equipment_id"] = equipment_id
        times = _DATETIME_RE.findall(query)
        if len(times) >= 2:
            arguments.update(start_at=times[0], end_at=times[1])
        purpose = re.search(r"用途[：:]\s*(.+)", query)
        if purpose:
            arguments["purpose"] = purpose.group(1)[:500]
        return arguments
    if tool_name == "create_lab_maintenance_ticket":
        description = _EQUIPMENT_RE.sub("", query)
        for phrase in (
            "帮我",
            "请",
            "登记报修",
            "提交报修",
            "创建故障工单",
            "登记维修工单",
            "报修",
        ):
            description = description.replace(phrase, "")
        arguments = {"issue": query[:1000]} if len(description.strip(" ，。,:：")) >= 3 else {}
        if equipment_id:
            arguments["equipment_id"] = equipment_id
        if any(cue in query for cue in ("冒烟", "漏液", "起火", "触电", "爆裂")):
            arguments["priority"] = "urgent"
        return arguments
    return {}


def _knowledge_fallback(query: str, registry: ToolRegistry) -> AgentPlan:
    if "search_knowledge" in registry.names():
        return AgentPlan(
            steps=[
                PlanStep(
                    step_id=1,
                    goal="policy lookup",
                    tool_name="search_knowledge",
                    arguments={"query": query},
                    needs_retrieval=True,
                )
            ],
            rationale="fallback_knowledge",
        )
    return AgentPlan(steps=[], rationale="empty")


async def planner_node(state: AgentState, planner: Planner) -> dict:
    confirmed = state.get("confirmed_action")
    if confirmed is not None:
        return {
            "plan": AgentPlan(
                steps=[
                    PlanStep(
                        step_id=1,
                        goal="confirmed action",
                        tool_name=confirmed.tool_name,
                        arguments=confirmed.arguments,
                    )
                ],
                rationale="confirmed_action",
            ),
            "pending_action": None,
        }
    intent = state.get("intent")
    query = state.get("resolved_query") or state["user_query"]
    plan = await planner.create_plan(
        query,
        intent.label.value if intent else "faq_policy",
        context_text(state),
    )
    requested_lab_write = _requested_lab_write_tool(query, planner._registry)
    if requested_lab_write:
        derived_arguments = _tool_arguments(requested_lab_write, query)
        matching_step = next(
            (step for step in plan.steps if step.tool_name == requested_lab_write), None
        )
        if matching_step is None:
            next_step_id = max((step.step_id for step in plan.steps), default=0) + 1
            plan = plan.model_copy(
                update={
                    "steps": [
                        *plan.steps,
                        PlanStep(
                            step_id=next_step_id,
                            goal="explicit lab write request",
                            tool_name=requested_lab_write,
                            arguments=derived_arguments,
                        ),
                    ]
                }
            )
        # Equipment IDs for writes must be explicitly present in the grounded query.
        # A model placeholder or invented ID must never become a confirmation proposal.
        if not _EQUIPMENT_RE.search(query):
            for step in plan.steps:
                if step.tool_name == requested_lab_write:
                    step.arguments.pop("equipment_id", None)
        if (
            requested_lab_write == "create_lab_maintenance_ticket"
            and "issue" not in derived_arguments
        ):
            for step in plan.steps:
                if step.tool_name == requested_lab_write:
                    step.arguments.pop("issue", None)
        else:
            plan = plan.model_copy(
                update={
                    "steps": [
                        step.model_copy(
                            update={"arguments": {**step.arguments, **derived_arguments}}
                        )
                        if step is matching_step
                        else step
                        for step in plan.steps
                    ]
                }
            )
    write_steps = [
        step
        for step in plan.steps
        if step.tool_name and planner._registry.get(step.tool_name).risk in WRITE_RISKS
    ]
    explicit_writes = [
        step for step in write_steps if _explicit_write_request(query, step.tool_name or "")
    ]
    incomplete = [
        (step, _missing_action_fields(step.tool_name or "", step.arguments))
        for step in explicit_writes
    ]
    incomplete = [(step, fields) for step, fields in incomplete if fields]
    if incomplete:
        step, fields = incomplete[0]
        extra = {"missing_action_fields": fields}
        return {"plan": plan.model_copy(update={"steps": []}), "extra": extra}
    plan = plan.model_copy(
        update={
            "steps": [
                step
                for step in plan.steps
                if step not in write_steps or _explicit_write_request(query, step.tool_name or "")
            ]
        }
    )
    pending = None
    for step in plan.steps:
        if not step.tool_name:
            continue
        tool = planner._registry.get(step.tool_name)
        if tool.risk in WRITE_RISKS and not state.get("confirm_action_id"):
            pending = ActionProposal(
                action_id=new_id("act_"),
                tool_name=tool.name,
                arguments=step.arguments,
                risk=tool.risk,
                summary=_action_summary(tool.name, step.arguments),
            )
            break
    return {"plan": plan, "pending_action": pending}


def _requested_lab_write_tool(query: str, registry: ToolRegistry) -> str | None:
    for tool_name in (
        "create_lab_maintenance_ticket",
        "request_lab_equipment_reservation",
    ):
        if tool_name in registry.names() and _explicit_write_request(query, tool_name):
            return tool_name
    return None


def _explicit_write_request(query: str, tool_name: str) -> bool:
    if any(cue in query for cue in ("规则", "政策", "条件", "怎么", "能不能", "是否", "可以吗")):
        return False
    if tool_name == "request_lab_equipment_reservation":
        return any(cue in query for cue in ("帮我预约", "提交预约", "申请预约", "替我预约"))
    if tool_name == "create_lab_maintenance_ticket":
        return any(
            cue in query
            for cue in ("帮我报修", "登记报修", "提交报修", "创建故障工单", "登记维修工单")
        )
    return False


def _missing_action_fields(tool_name: str, arguments: dict) -> list[str]:
    required = {
        "request_lab_equipment_reservation": ("equipment_id", "start_at", "end_at", "purpose"),
        "create_lab_maintenance_ticket": ("equipment_id", "issue"),
    }.get(tool_name, ())
    placeholders = {"待用户提供", "待补充", "未知", "unknown", "n/a", "null", "none"}
    return [
        field
        for field in required
        if not arguments.get(field) or str(arguments[field]).strip().lower() in placeholders
    ]


def _action_summary(tool_name: str, arguments: dict) -> str:
    equipment_id = arguments.get("equipment_id", "该设备")
    if tool_name == "request_lab_equipment_reservation":
        start_at = arguments.get("start_at", "所选时段")
        end_at = arguments.get("end_at", "")
        return f"确认后将为 {equipment_id} 提交预约申请（{start_at} 至 {end_at}）；最终预约仍需管理员审核。"
    if tool_name == "create_lab_maintenance_ticket":
        return f"确认后将为 {equipment_id} 登记报修工单，供设备管理员审核；系统不会自动维修设备。"
    return "确认后将提交该操作。"
