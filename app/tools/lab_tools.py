"""Tools for shared university laboratory equipment and service workflows."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.enums import ToolRisk
from app.schemas.agent import ToolResult
from app.tools.base import Tool, ToolContext
from app.tools.deps import LabRepositoryBackedTool


class EquipmentSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=100)


class EquipmentIdInput(BaseModel):
    equipment_id: str = Field(min_length=5, max_length=32, pattern=r"^LAB-[A-Z0-9-]+$")


class EquipmentAvailabilityInput(EquipmentIdInput):
    date: date


class ReservationRequestInput(EquipmentIdInput):
    start_at: datetime
    end_at: datetime
    purpose: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_window(self):
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("start_at and end_at must include a timezone")
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be later than start_at")
        return self


class MaintenanceRequestInput(EquipmentIdInput):
    issue: str = Field(min_length=5, max_length=1000)
    priority: Literal["normal", "urgent"] = "normal"


class SearchEquipmentTool(LabRepositoryBackedTool, Tool):
    name = "search_lab_equipment"
    description = (
        "按设备名称、类别或实验室位置查询共享仪器台账。"
        "何时用：用户想知道有哪些设备或某类设备在哪。只返回本项目的演示台账。"
    )
    risk = ToolRisk.READ
    input_model = EquipmentSearchInput

    async def execute(self, parsed: EquipmentSearchInput, context: ToolContext) -> ToolResult:
        return ToolResult(
            name=self.name,
            success=True,
            output={"equipment": await self.repository.list_equipment(parsed.query)},
        )


class GetEquipmentStatusTool(LabRepositoryBackedTool, Tool):
    name = "get_lab_equipment_status"
    description = (
        "按设备编号查询共享仪器台账状态和位置。设备编号格式如 LAB-CF-01。"
        "此状态是项目演示数据，不代表任何真实学校设备的实时遥测。"
    )
    risk = ToolRisk.READ
    input_model = EquipmentIdInput

    async def execute(self, parsed: EquipmentIdInput, context: ToolContext) -> ToolResult:
        return ToolResult(
            name=self.name,
            success=True,
            output=await self.repository.get_equipment(parsed.equipment_id),
        )


class CheckEquipmentAvailabilityTool(LabRepositoryBackedTool, Tool):
    name = "check_lab_equipment_availability"
    description = (
        "查询指定设备某日的演示预约申请和占用时段。"
        "预约申请不代表管理员已批准；设备最终可用性须以校内预约平台为准。"
    )
    risk = ToolRisk.READ
    input_model = EquipmentAvailabilityInput

    async def execute(self, parsed: EquipmentAvailabilityInput, context: ToolContext) -> ToolResult:
        return ToolResult(
            name=self.name,
            success=True,
            output=await self.repository.check_availability(parsed.equipment_id, parsed.date),
        )


class RequestEquipmentReservationTool(LabRepositoryBackedTool, Tool):
    name = "request_lab_equipment_reservation"
    description = (
        "向项目演示数据库提交一条共享设备预约申请，不会直接确认预约或授予设备操作资格。"
        "必须有设备编号、含时区的开始/结束时间和用途；属于写操作，需用户二次确认。"
    )
    risk = ToolRisk.WRITE
    input_model = ReservationRequestInput

    async def execute(self, parsed: ReservationRequestInput, context: ToolContext) -> ToolResult:
        result = await self.repository.create_reservation_request(
            equipment_id=parsed.equipment_id,
            user_id=context.user_id,
            start_at=parsed.start_at,
            end_at=parsed.end_at,
            purpose=parsed.purpose,
            trace_id=context.trace_id,
        )
        return ToolResult(name=self.name, success=True, output=result, risk=self.risk)


class CreateMaintenanceTicketTool(LabRepositoryBackedTool, Tool):
    name = "create_lab_maintenance_ticket"
    description = (
        "登记设备故障工单供实验室管理员审核，不会自动停机、维修或联系厂商。"
        "必须有设备编号和具体故障现象；属于写操作，需用户二次确认。"
    )
    risk = ToolRisk.WRITE
    input_model = MaintenanceRequestInput

    async def execute(self, parsed: MaintenanceRequestInput, context: ToolContext) -> ToolResult:
        result = await self.repository.create_maintenance_ticket(
            equipment_id=parsed.equipment_id,
            user_id=context.user_id,
            issue=parsed.issue,
            priority=parsed.priority,
            trace_id=context.trace_id,
        )
        return ToolResult(name=self.name, success=True, output=result, risk=self.risk)
