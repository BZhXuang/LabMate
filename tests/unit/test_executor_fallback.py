import pytest
from pydantic import BaseModel, Field

from app.agents.nodes.executor import execute_with_fallback
from app.core.enums import ToolRisk
from app.core.exceptions import ToolExecutionError
from app.schemas.agent import PlanStep, ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.registry import ToolRegistry


class _Query(BaseModel):
    query: str = Field(default="")


class _FailingEquipmentStatus(Tool):
    name = "get_lab_equipment_status"
    description = "fail"
    risk = ToolRisk.READ
    input_model = _Query

    async def execute(self, parsed: BaseModel, context: ToolContext) -> ToolResult:
        raise ToolExecutionError("equipment status lookup failed")


class _Knowledge(Tool):
    name = "search_knowledge"
    description = "kb"
    risk = ToolRisk.READ
    input_model = _Query

    async def execute(self, parsed: BaseModel, context: ToolContext) -> ToolResult:
        return ToolResult(name=self.name, success=True, output={"chunks": [{"content": "政策"}]})


@pytest.mark.asyncio
async def test_read_tool_falls_back_to_knowledge() -> None:
    registry = ToolRegistry()
    registry.register(_FailingEquipmentStatus())
    registry.register(_Knowledge())
    result = await execute_with_fallback(
        registry.get("get_lab_equipment_status"),
        PlanStep(
            step_id=1,
            goal="equipment status",
            tool_name="get_lab_equipment_status",
            arguments={"equipment_id": "LAB-CF-01"},
        ),
        ToolContext(user_id="u", session_id="s", trace_id="t"),
        registry,
        "LAB-CF-01 当前状态如何",
    )
    assert result.success is True
    assert result.name == "search_knowledge"
    assert result.output["fallback_from"] == "get_lab_equipment_status"
