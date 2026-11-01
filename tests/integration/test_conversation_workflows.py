from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.config.settings import Settings
from app.core.exceptions import InvalidRequestError
from app.core.time import utcnow
from app.memory.context import context_text, resolve_context_node
from app.providers.fake import OfflineLLMProvider
from app.repositories.action_repository import ActionRepository
from app.repositories.models import LabMaintenanceTicketRow, LabReservationRow, PendingActionRow
from app.repositories.session_repository import SessionRepository
from app.schemas.chat import ChatMessage, ChatRequest
from app.services.container import build_container


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["reservation", "maintenance"])
async def test_propose_restart_confirm_retry_and_read_database(tmp_path, kind):
    settings = Settings(
        app_env="testing",
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'workflow.db').as_posix()}",
        local_embedding_enabled=False,
        cross_encoder_enabled=False,
    )
    start = (utcnow() + timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0)
    query = (
        f"帮我预约 LAB-CF-01 从 {start.isoformat()} 至 {(start + timedelta(hours=1)).isoformat()}，用途：测试样品"
        if kind == "reservation"
        else "LAB-CF-01 持续振动，帮我登记报修"
    )
    model = LabReservationRow if kind == "reservation" else LabMaintenanceTicketRow
    container = await build_container(settings)
    proposal = await container.chat_service.chat(
        ChatRequest(message=query, user_id="owner"), trace_id="propose"
    )
    assert proposal.pending_action is not None
    async with container.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(model)) == 0
        await SessionRepository(db).save_summary(
            proposal.session_id, "正在处理 LAB-CF-01，用户用途是测试样品。"
        )
        await db.commit()
    await container.aclose()
    # New engine, connection pool, providers, compiled graph and ChatService.
    container = await build_container(settings)
    try:
        request = ChatRequest(
            message="确认执行",
            user_id="owner",
            session_id=proposal.session_id,
            confirm_action_id=proposal.pending_action.action_id,
        )
        result = await container.chat_service.chat(request, trace_id="confirmed")
        assert result.pending_action is None
        assert "已登记" in result.answer
        again = await container.chat_service.chat(request, trace_id="retry")
        assert again.answer == result.answer
        async with container.session_factory() as db:
            assert await db.scalar(select(func.count()).select_from(model)) == 1
            state = await container.chat_service._initial_state(
                db,
                request.model_copy(update={"confirm_action_id": None}),
                proposal.session_id,
                "restored",
            )
            assert "测试样品" in state["summary"]
            assert state["messages"]
            with pytest.raises(InvalidRequestError, match="不属于"):
                await container.chat_service._initial_state(
                    db,
                    request.model_copy(update={"user_id": "intruder"}),
                    proposal.session_id,
                    "forged",
                )
            action = await db.get(PendingActionRow, request.confirm_action_id)
            action.expires_at = utcnow() - timedelta(seconds=1)
            await db.commit()
        async with container.session_factory() as db:
            with pytest.raises(InvalidRequestError, match="过期"):
                await ActionRepository(db).resolve(
                    request.confirm_action_id, session_id=proposal.session_id, user_id="owner"
                )
    finally:
        await container.aclose()


@pytest.mark.asyncio
async def test_followup_resolves_one_user_referent_but_does_not_guess_from_multiple():
    llm = OfflineLLMProvider()
    state = {
        "user_query": "它在哪里？",
        "messages": [ChatMessage(role="user", content="查 LAB-CF-01 的状态")],
    }
    assert (await resolve_context_node(state, llm=llm))["resolved_query"] == "LAB-CF-01在哪里？"
    state["messages"] = [ChatMessage(role="user", content="比较 LAB-CF-01 和 LAB-LSM-02")]
    assert (await resolve_context_node(state, llm=llm))["resolved_query"] == "它在哪里？"


@pytest.mark.asyncio
async def test_generator_receives_bounded_history_and_summary():
    from app.agents.nodes.generate import generate_node
    from app.core.enums import RetrievalStrategy
    from app.providers.base import LLMResponse

    class Capture:
        async def generate(self, messages, **kwargs):
            self.messages = messages
            return LLMResponse(content='{"answer":"上下文中的样品代号是 ALPHA-7。"}')

    llm = Capture()
    state = {
        "user_query": "之前的样品代号是什么？",
        "strategy": RetrievalStrategy.DIRECT,
        "summary": "用户样品代号 ALPHA-7。",
        "messages": [ChatMessage(role="user", content="记住样品代号")],
    }
    await generate_node(state, llm)
    assert "ALPHA-7" in llm.messages[-1]["content"]
    assert "记住样品代号" in llm.messages[-1]["content"]
    assert (
        len(
            context_text(
                {
                    "messages": [ChatMessage(role="user", content="x" * 10000)] * 30,
                    "summary": "y" * 10000,
                }
            )
        )
        <= 6800
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("resolved", ["帮我预约 LAB-CF-01", "查询 LAB-FAKE-99 的状态"])
async def test_context_resolution_rejects_new_write_authorization_and_invented_ids(resolved):
    import json

    from app.providers.fake import FakeLLMProvider

    state = {
        "user_query": "刚才那项是什么？",
        "messages": [ChatMessage(role="user", content="查 LAB-CF-01 的状态")],
    }
    llm = FakeLLMProvider({"": json.dumps({"query": resolved})})
    assert (await resolve_context_node(state, llm=llm))["resolved_query"] == state["user_query"]


def test_confirmation_survives_two_separate_python_processes(tmp_path):
    import json
    import os
    import subprocess
    import sys

    program = """
import asyncio,json,sys
from pathlib import Path
from app.config.settings import Settings
from app.schemas.chat import ChatRequest
from app.services.container import build_container
async def main():
    c=await build_container(Settings(app_env="testing",database_url=sys.argv[1],local_embedding_enabled=False,cross_encoder_enabled=False))
    try:
        p=Path(sys.argv[3])
        if sys.argv[2]=="propose":
            r=await c.chat_service.chat(ChatRequest(message="LAB-CF-01 持续振动，帮我登记报修",user_id="process_owner"),trace_id="proc1")
            p.write_text(r.model_dump_json(),encoding="utf-8")
        else:
            old=json.loads(p.read_text(encoding="utf-8"))
            r=await c.chat_service.chat(ChatRequest(message="确认执行",user_id="process_owner",session_id=old["session_id"],confirm_action_id=old["pending_action"]["action_id"]),trace_id="proc2")
            assert "已登记" in r.answer, r.answer
            p.write_text(r.model_dump_json(),encoding="utf-8")
    finally:
        await c.aclose()
asyncio.run(main())
"""
    database = f"sqlite+aiosqlite:///{(tmp_path/'process.db').as_posix()}"
    output = tmp_path / "response.json"
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "DEEPSEEK_API_KEY": "",
        "EMBEDDING_API_KEY": "",
    }
    for phase in ("propose", "confirm"):
        result = subprocess.run(
            [sys.executable, "-c", program, database, phase, str(output)],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
    assert "已登记" in json.loads(output.read_text(encoding="utf-8"))["answer"]


@pytest.mark.asyncio
async def test_streamed_proposal_is_persisted_before_the_answer_event(tmp_path):
    settings = Settings(
        app_env="testing",
        database_url=f"sqlite+aiosqlite:///{(tmp_path/'stream.db').as_posix()}",
        local_embedding_enabled=False,
        cross_encoder_enabled=False,
    )
    container = await build_container(settings)
    try:
        events = [
            event
            async for event in container.chat_service.stream(
                ChatRequest(message="LAB-CF-01 持续振动，帮我登记报修", user_id="stream_owner"),
                trace_id="stream_propose",
            )
        ]
        answer = next(e["data"] for e in events if e["event"] == "answer")
        async with container.session_factory() as db:
            stored = await ActionRepository(db).resolve(
                answer["pending_action"]["action_id"],
                session_id=answer["session_id"],
                user_id="stream_owner",
            )
            assert stored.tool_name == "create_lab_maintenance_ticket"
            assert await db.scalar(select(func.count()).select_from(LabMaintenanceTicketRow)) == 0
    finally:
        await container.aclose()
