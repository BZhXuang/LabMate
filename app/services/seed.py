"""Seed fictional equipment rows for local demonstrations only."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.models import LabEquipmentRow


async def seed_lab_demo_data(session: AsyncSession) -> None:
    """Insert missing demo rows without changing existing records."""
    equipment = [
        LabEquipmentRow(
            equipment_id="LAB-CF-01",
            name="台式冷冻离心机（演示设备）",
            category="样品前处理",
            location="A楼 203 仪器间",
            status="available",
            requires_training=True,
            notes="演示台账；本系统不采集真实设备遥测。使用前须按本校流程培训。",
        ),
        LabEquipmentRow(
            equipment_id="LAB-LSM-02",
            name="激光共聚焦显微镜（演示设备）",
            category="显微成像",
            location="B楼 415 公共仪器平台",
            status="available",
            requires_training=True,
            notes="演示台账；预约与培训要求以实际管理平台为准。",
        ),
        LabEquipmentRow(
            equipment_id="LAB-AC-01",
            name="高压蒸汽灭菌器（演示设备）",
            category="灭菌设备",
            location="A楼 108 公共实验区",
            status="maintenance",
            requires_training=True,
            notes="演示台账中标记为维护中；不得据此判断任何真实设备状态。",
        ),
    ]
    for row in equipment:
        if await session.get(LabEquipmentRow, row.equipment_id) is None:
            session.add(row)
