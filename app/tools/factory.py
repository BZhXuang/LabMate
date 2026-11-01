"""Build the LabMate-only tool registry."""

from app.retrieval.hybrid import HybridRetriever
from app.tools.base import Tool
from app.tools.knowledge_tools import SearchKnowledgeTool
from app.tools.lab_tools import (
    CheckEquipmentAvailabilityTool,
    CreateMaintenanceTicketTool,
    GetEquipmentStatusTool,
    RequestEquipmentReservationTool,
    SearchEquipmentTool,
)
from app.tools.registry import ToolRegistry


def build_tool_registry(retriever: HybridRetriever) -> ToolRegistry:
    """Build the six active LabMate tools."""
    registry = ToolRegistry()
    tools: list[Tool] = [
        SearchEquipmentTool(),
        GetEquipmentStatusTool(),
        CheckEquipmentAvailabilityTool(),
        RequestEquipmentReservationTool(),
        CreateMaintenanceTicketTool(),
        SearchKnowledgeTool(retriever),
    ]
    for tool in tools:
        registry.register(tool)
    return registry
