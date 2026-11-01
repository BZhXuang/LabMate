import pytest

from app.agents.nodes.planner import Planner, planner_node
from app.core.enums import IntentLabel, ToolRisk
from app.core.exceptions import InvalidRequestError
from app.providers.fake import FakeLLMProvider
from app.schemas.agent import IntentResult
from app.schemas.chat import ActionProposal, ChatRequest
from app.services.chat_service import ChatService
from app.tools.lab_tools import CreateMaintenanceTicketTool
from app.tools.registry import ToolRegistry


def _action() -> ActionProposal:
    return ActionProposal(
        action_id="act_test",
        tool_name="create_lab_maintenance_ticket",
        arguments={"equipment_id": "LAB-CF-01", "issue": "运行时持续振动"},
        risk=ToolRisk.WRITE,
        summary="确认后将登记设备故障工单。",
    )


@pytest.mark.asyncio
async def test_explicit_maintenance_request_always_proposes_confirmation() -> None:
    query = "LAB-CF-01 运行时持续振动，帮我登记报修"
    llm = FakeLLMProvider(
        {
            "LAB-CF-01": (
                '{"steps":[{"step_id":1,"goal":"review policy",'
                '"tool_name":null,"arguments":{}}],"rationale":"read first"}'
            )
        }
    )
    registry = ToolRegistry()
    registry.register(CreateMaintenanceTicketTool())
    planner = Planner(llm, registry)

    proposal = await planner_node(
        {
            "user_query": query,
            "intent": IntentResult(
                label=IntentLabel.LAB_MAINTENANCE,
                confidence=1.0,
                prompt_version="test",
            ),
        },
        planner,
    )

    action = proposal["pending_action"]
    assert action is not None
    assert action.tool_name == "create_lab_maintenance_ticket"
    assert action.arguments["equipment_id"] == "LAB-CF-01"
    assert action.arguments["issue"] == query


@pytest.mark.asyncio
async def test_missing_equipment_and_issue_cannot_be_filled_by_model_placeholders():
    registry = ToolRegistry()
    registry.register(CreateMaintenanceTicketTool())
    llm = FakeLLMProvider(
        {
            "": '{"steps":[{"step_id":1,"goal":"report","tool_name":"create_lab_maintenance_ticket","arguments":{"equipment_id":"待用户提供","issue":"待补充"}}]}'
        }
    )
    result = await planner_node({"user_query": "帮我登记报修"}, Planner(llm, registry))
    assert result["extra"]["missing_action_fields"] == ["equipment_id", "issue"]
    assert not result["plan"].steps


@pytest.mark.asyncio
async def test_confirmation_is_bound_to_session_and_user() -> None:
    from app.config.settings import Settings
    from app.repositories.action_repository import ActionRepository
    from app.repositories.db import create_engine, create_session_factory, init_schema

    engine = create_engine(Settings(database_url="sqlite+aiosqlite:///:memory:"))
    await init_schema(engine)
    factory = create_session_factory(engine)
    service = ChatService.__new__(ChatService)
    try:
        async with factory() as db:
            await ActionRepository(db).save(_action(), session_id="sess_demo", user_id="u_demo")
            await db.commit()
        async with factory() as db:
            confirmed = ChatRequest(
                message="确认执行",
                user_id="u_demo",
                session_id="sess_demo",
                confirm_action_id="act_test",
            )
            assert await service._resolve_confirmation(db, confirmed, "sess_demo") == _action()
            with pytest.raises(InvalidRequestError):
                await service._resolve_confirmation(
                    db, confirmed.model_copy(update={"user_id": "someone_else"}), "sess_demo"
                )
            with pytest.raises(InvalidRequestError):
                await service._resolve_confirmation(db, confirmed, "another_session")
    finally:
        await engine.dispose()
