from datetime import UTC, datetime, timedelta

import pytest

from app.config.settings import Settings
from app.core.exceptions import InvalidRequestError
from app.repositories.db import create_engine, create_session_factory, init_schema
from app.repositories.lab_repository import LabRepository
from app.services.seed import seed_lab_demo_data


@pytest.mark.asyncio
async def test_demo_booking_conflict_and_maintenance_ticket_are_persisted() -> None:
    settings = Settings(
        app_env="testing",
        database_url="sqlite+aiosqlite:///:memory:",
        local_embedding_enabled=False,
        cross_encoder_enabled=False,
        unstructured_enabled=False,
    )
    engine = create_engine(settings)
    try:
        await init_schema(engine)
        sessions = create_session_factory(engine)
        async with sessions() as session:
            await seed_lab_demo_data(session)
            repo = LabRepository(session)
            start = datetime.now(UTC) + timedelta(days=2)
            end = start + timedelta(hours=2)
            booking = await repo.create_reservation_request(
                equipment_id="LAB-CF-01",
                user_id="u_demo",
                start_at=start,
                end_at=end,
                purpose="样品前处理",
                trace_id="tr_test_lab_booking",
            )
            assert booking["status"] == "requested"

            with pytest.raises(InvalidRequestError, match="overlaps"):
                await repo.create_reservation_request(
                    equipment_id="LAB-CF-01",
                    user_id="u_other",
                    start_at=start + timedelta(minutes=30),
                    end_at=end + timedelta(minutes=30),
                    purpose="重复时段验证",
                    trace_id="tr_test_lab_conflict",
                )

            ticket = await repo.create_maintenance_ticket(
                equipment_id="LAB-CF-01",
                user_id="u_demo",
                issue="运行中出现持续振动",
                priority="normal",
                trace_id="tr_test_lab_ticket",
            )
            assert ticket["status"] == "open"
            await session.commit()

        async with sessions() as session:
            availability = await LabRepository(session).check_availability(
                "LAB-CF-01", start.date()
            )
            assert len(availability["bookings"]) == 1
            assert availability["bookings"][0]["status"] == "requested"
    finally:
        await engine.dispose()
