"""Repository for the LabMate shared-instrument demo domain."""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidRequestError
from app.core.ids import new_id
from app.core.time import utcnow
from app.repositories.models import (
    AuditLogRow,
    LabEquipmentRow,
    LabMaintenanceTicketRow,
    LabReservationRow,
)


class LabRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_equipment(self, query: str = "") -> list[dict]:
        statement = select(LabEquipmentRow).order_by(LabEquipmentRow.equipment_id)
        if query.strip():
            term = f"%{query.strip()}%"
            statement = statement.where(
                LabEquipmentRow.equipment_id.ilike(term)
                | LabEquipmentRow.name.ilike(term)
                | LabEquipmentRow.category.ilike(term)
                | LabEquipmentRow.location.ilike(term)
            )
        rows = (await self._session.execute(statement)).scalars().all()
        return [_equipment_payload(row) for row in rows]

    async def get_equipment(self, equipment_id: str) -> dict:
        row = await self._session.get(LabEquipmentRow, equipment_id.upper())
        if row is None:
            raise InvalidRequestError(f"equipment not found: {equipment_id}")
        return _equipment_payload(row)

    async def check_availability(self, equipment_id: str, day: date) -> dict:
        equipment = await self._session.get(LabEquipmentRow, equipment_id.upper())
        if equipment is None:
            raise InvalidRequestError(f"equipment not found: {equipment_id}")
        start = datetime.combine(day, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        statement = (
            select(LabReservationRow)
            .where(
                LabReservationRow.equipment_id == equipment.equipment_id,
                LabReservationRow.start_at < end,
                LabReservationRow.end_at > start,
                LabReservationRow.status.in_(("requested", "approved")),
            )
            .order_by(LabReservationRow.start_at)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return {
            "equipment": _equipment_payload(equipment),
            "date": day.isoformat(),
            "can_request": equipment.status == "available",
            "bookings": [_reservation_payload(row) for row in rows],
            "note": "演示系统仅接收预约申请，最终时段以管理员审核为准。",
        }

    async def create_reservation_request(
        self,
        *,
        equipment_id: str,
        user_id: str,
        start_at: datetime,
        end_at: datetime,
        purpose: str,
        trace_id: str,
    ) -> dict:
        equipment = await self._session.get(LabEquipmentRow, equipment_id.upper())
        if equipment is None:
            raise InvalidRequestError(f"equipment not found: {equipment_id}")
        if equipment.status != "available":
            raise InvalidRequestError("equipment is not accepting reservation requests")
        start = _as_utc(start_at)
        end = _as_utc(end_at)
        if start <= utcnow():
            raise InvalidRequestError("reservation start must be in the future")
        if end <= start or end - start > timedelta(hours=8):
            raise InvalidRequestError("reservation must be positive and no longer than 8 hours")
        conflict = await self._session.scalar(
            select(LabReservationRow.reservation_id).where(
                LabReservationRow.equipment_id == equipment.equipment_id,
                LabReservationRow.start_at < end,
                LabReservationRow.end_at > start,
                LabReservationRow.status.in_(("requested", "approved")),
            )
        )
        if conflict:
            raise InvalidRequestError("requested time overlaps an existing request or booking")
        row = LabReservationRow(
            reservation_id=new_id("res_")[:24],
            equipment_id=equipment.equipment_id,
            user_id=user_id,
            start_at=start,
            end_at=end,
            purpose=purpose.strip(),
            status="requested",
        )
        self._session.add(row)
        await self._audit(trace_id, "create_lab_reservation_request", row.reservation_id)
        await self._session.flush()
        return _reservation_payload(row)

    async def create_maintenance_ticket(
        self,
        *,
        equipment_id: str,
        user_id: str,
        issue: str,
        priority: str,
        trace_id: str,
    ) -> dict:
        equipment = await self._session.get(LabEquipmentRow, equipment_id.upper())
        if equipment is None:
            raise InvalidRequestError(f"equipment not found: {equipment_id}")
        row = LabMaintenanceTicketRow(
            ticket_id=new_id("mt_")[:24],
            equipment_id=equipment.equipment_id,
            user_id=user_id,
            issue=issue.strip(),
            priority=priority,
            status="open",
            trace_id=trace_id,
        )
        self._session.add(row)
        await self._audit(trace_id, "create_lab_maintenance_ticket", row.ticket_id)
        await self._session.flush()
        return {
            "ticket_id": row.ticket_id,
            "equipment_id": row.equipment_id,
            "status": row.status,
            "priority": row.priority,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "message": "报修单已登记，维修安排仍需设备管理员审核。",
        }

    async def _audit(self, trace_id: str, action: str, record_id: str) -> None:
        self._session.add(
            AuditLogRow(trace_id=trace_id, action=action, payload=record_id)
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise InvalidRequestError("datetime must include a timezone")
    return value.astimezone(UTC)


def _equipment_payload(row: LabEquipmentRow) -> dict:
    return {
        "equipment_id": row.equipment_id,
        "name": row.name,
        "category": row.category,
        "location": row.location,
        "status": row.status,
        "requires_training": row.requires_training,
        "notes": row.notes,
    }


def _reservation_payload(row: LabReservationRow) -> dict:
    return {
        "reservation_id": row.reservation_id,
        "equipment_id": row.equipment_id,
        "start_at": row.start_at.isoformat(),
        "end_at": row.end_at.isoformat(),
        "status": row.status,
        "purpose": row.purpose,
    }
