"""Real-model E2E scenarios with multi-turn state and database assertions."""

from __future__ import annotations

import sys
import tempfile
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select

from eval.metrics import percentile


async def evaluate_workflows(rows: list[dict]) -> dict:
    from app.config.settings import clear_settings_cache, get_settings
    from app.infra.rate_limit import InMemoryRateLimiter
    from app.repositories.db import create_engine, create_session_factory, init_schema
    from app.repositories.lab_repository import LabRepository
    from app.repositories.models import LabMaintenanceTicketRow, LabReservationRow, SessionRow
    from app.schemas.chat import ChatRequest
    from app.services.chat_service import ChatService
    from app.services.container import build_container

    clear_settings_cache()
    settings = get_settings()
    if not settings.llm_configured:
        raise SystemExit("DEEPSEEK_API_KEY missing")
    # Never mutate the developer's database or share records between evaluation runs.
    directory = Path("data/local")
    directory.mkdir(parents=True, exist_ok=True)
    temp = tempfile.TemporaryDirectory(prefix="e2e-v2-", dir=directory)
    database = (Path(temp.name) / "workflows.db").resolve()
    settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{database.as_posix()}",
            "rate_limit_per_minute": 10000,
            "redis_url": "",
            "qdrant_url": "",
        }
    )
    container = await build_container(settings)
    totals: dict[str, list[bool]] = defaultdict(list)
    stage_ms: dict[str, list[float]] = defaultdict(list)
    scenarios = []
    restarts = 0

    async def counts(user_id: str) -> dict[str, int]:
        async with container.session_factory() as db:
            return {
                key: int(
                    await db.scalar(
                        select(func.count()).select_from(model).where(model.user_id == user_id)
                    )
                    or 0
                )
                for key, model in (
                    ("ticket", LabMaintenanceTicketRow),
                    ("reservation", LabReservationRow),
                )
            }

    async def restart_service() -> None:
        nonlocal restarts
        registry = container.chat_service.registry
        reranker = container.chat_service._reranker
        await container.engine.dispose()
        container.engine = create_engine(settings)
        await init_schema(container.engine)
        container.session_factory = create_session_factory(container.engine)
        container.chat_service = ChatService(
            settings=settings,
            llm=container.llm,
            retriever=container.retriever,
            reranker=reranker,
            session_factory=container.session_factory,
            rate_limiter=InMemoryRateLimiter(limit=10000),
            registry=registry,
        )
        restarts += 1

    try:
        for index, row in enumerate(rows):
            user_id = f"eval_{row['id']}"
            session_id = None
            previous_action = None
            start = (datetime.now(UTC) + timedelta(days=30 + index)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            params = {
                "start_at": start.isoformat(),
                "end_at": (start + timedelta(hours=1)).isoformat(),
                "date": start.date().isoformat(),
            }
            turns = []
            for turn_index, step in enumerate(row.get("steps") or [row]):
                query = step["query"].format(**params)
                checks = {}
                detail = {"turn": turn_index + 1, "query": query}
                try:
                    if step.get("restart_before"):
                        await restart_service()
                    before = await counts(user_id)
                    if step.get("confirm_previous") and previous_action is None:
                        raise ValueError("No proposal to confirm in this scenario")
                    request = ChatRequest(
                        message=query,
                        user_id=user_id,
                        session_id=session_id,
                        confirm_action_id=previous_action if step.get("confirm_previous") else None,
                    )
                    started = time.perf_counter()
                    response = await container.chat_service.chat(
                        request, trace_id=f"eval_{row['id']}_{turn_index + 1}"
                    )
                    duration = (time.perf_counter() - started) * 1000
                    stage_ms["total"].append(duration)
                    for key in ("intent", "retrieval", "llm", "tool"):
                        stage_ms[key].append(getattr(response.latency, key + "_ms"))
                    session_id = response.session_id
                    if response.pending_action:
                        previous_action = response.pending_action.action_id
                    after = await counts(user_id)
                    for key in ("strategy", "intent"):
                        if step.get("expect_" + key):
                            actual = getattr(response, key)
                            checks[key] = (
                                actual is not None and actual.value == step["expect_" + key]
                            )
                    if "expect_refused" in step:
                        checks["refuse"] = response.refused == step["expect_refused"]
                    if step.get("expect_keywords"):
                        checks["keyword"] = all(
                            word in response.answer for word in step["expect_keywords"]
                        )
                    if step.get("expect_pending_tool"):
                        checks["pending_tool"] = bool(
                            response.pending_action
                            and response.pending_action.tool_name == step["expect_pending_tool"]
                        )
                    for key in ("ticket", "reservation"):
                        if "expect_" + key + "_delta" in step:
                            checks[key + "_delta"] = (
                                after[key] - before[key] == step["expect_" + key + "_delta"]
                            )
                    if step.get("expect_no_write"):
                        checks["no_write"] = before == after
                    if "expect_booking_count" in step:
                        async with container.session_factory() as db:
                            availability = await LabRepository(db).check_availability(
                                "LAB-CF-01", start.date()
                            )
                        checks["readback"] = (
                            len(availability["bookings"]) == step["expect_booking_count"]
                        )
                    if step.get("expect_summary_present"):
                        async with container.session_factory() as db:
                            saved = await db.get(SessionRow, session_id)
                            checks["summary_restored"] = bool(
                                saved and saved.summary and "ALPHA-7" in saved.summary
                            )
                    if step.get("expect_strategy") == "multi":
                        checks["multi_executed"] = (
                            response.strategy is not None
                            and response.strategy.value == "multi"
                            and response.retrieval_rounds > 0
                        )
                    checks["completed"] = True
                    detail.update(response.model_dump(mode="json"))
                    detail.update(
                        database_before=before, database_after=after, latency_ms=round(duration, 1)
                    )
                except Exception as exc:
                    checks["completed"] = False
                    detail.update(error_type=type(exc).__name__, error=str(exc)[:300])
                for key, value in checks.items():
                    totals[key].append(value)
                detail["checks"] = checks
                detail["passed"] = all(checks.values())
                turns.append(detail)
            scenarios.append(
                {
                    "id": row["id"],
                    "name": row.get("name"),
                    "passed": all(t["passed"] for t in turns),
                    "turns": turns,
                }
            )
            print(
                f"E2E {index + 1}/{len(rows)} {row['id']}: {'PASS' if scenarios[-1]['passed'] else 'FAIL'}",
                file=sys.stderr,
                flush=True,
            )
    finally:
        await container.aclose()
        temp.cleanup()
    ratios = {
        key: {"passed": sum(values), "n": len(values), "rate": round(sum(values) / len(values), 4)}
        for key, values in totals.items()
    }
    durations = stage_ms["total"]
    return {
        "n": len(rows),
        "turns": sum(len(s["turns"]) for s in scenarios),
        "scenario_passed": sum(s["passed"] for s in scenarios),
        "scenario_pass_rate": round(sum(s["passed"] for s in scenarios) / len(rows), 4)
        if rows
        else 0,
        "refuse_accuracy": ratios.get("refuse", {}).get("rate"),
        "keyword_hit": ratios.get("keyword", {}).get("rate"),
        "strategy_accuracy": ratios.get("strategy", {}).get("rate"),
        "intent_accuracy": ratios.get("intent", {}).get("rate"),
        "pending_tool_hit": ratios.get("pending_tool", {}).get("rate"),
        "checks": ratios,
        "service_restarts": restarts,
        "latency_ms": {
            "p50": round(percentile(durations, 50), 1),
            "p95": round(percentile(durations, 95), 1),
            "mean": round(sum(durations) / len(durations), 1) if durations else 0,
            **{
                key + "_p50": round(percentile(stage_ms[key], 50), 1)
                for key in ("intent", "retrieval", "llm", "tool")
            },
        },
        "cases": scenarios,
        "protocol": "32 scenarios; generated UTC windows; isolated file SQLite; fresh service/engine on restart, providers reused; all failures kept. Keyword matching is lexical, not independent correctness. No production DB writes.",
    }
