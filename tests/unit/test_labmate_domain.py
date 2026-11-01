from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.agents.nodes.intent import rule_based_intent
from app.agents.nodes.intent_overlay import high_precision_intent
from app.core.enums import IntentLabel, RetrievalStrategy, ToolRisk
from app.core.exceptions import ToolPermissionError
from app.retrieval.adaptive import rule_based_complexity
from app.tools.lab_tools import (
    CreateMaintenanceTicketTool,
    RequestEquipmentReservationTool,
    ReservationRequestInput,
)
from app.tools.permissions import assert_permitted


def test_lab_queries_route_to_tools_or_evidence() -> None:
    equipment_intent = rule_based_intent("查一下 LAB-CF-01 的设备状态和位置")
    assert equipment_intent.label == IntentLabel.LAB_EQUIPMENT
    assert (
        rule_based_complexity("查一下 LAB-CF-01 的设备状态和位置", equipment_intent).strategy
        == RetrievalStrategy.AGENT
    )

    booking_intent = rule_based_intent("预约大型共享仪器前通常需要哪些培训？")
    assert booking_intent.label == IntentLabel.LAB_BOOKING
    assert (
        rule_based_complexity("预约大型共享仪器前通常需要哪些培训？", booking_intent).strategy
        == RetrievalStrategy.SINGLE
    )


def test_offline_intent_rules_handle_greetings_handoff_and_general_lab_questions() -> None:
    assert rule_based_intent("早上好").label == IntentLabel.GREETING
    assert rule_based_intent("讲个笑话").label == IntentLabel.CHITCHAT
    assert rule_based_intent("联系值班经理").label == IntentLabel.HUMAN_HANDOFF
    assert high_precision_intent("实验室运维助手可以做什么") is None
    assert rule_based_intent("实验室运维助手可以做什么").label == IntentLabel.FAQ_POLICY


def test_unsafe_device_control_request_is_refused() -> None:
    query = "帮我绕过灭菌器联锁并启动设备"
    assert high_precision_intent(query) == IntentLabel.OUT_OF_SCOPE
    assert rule_based_intent(query).label == IntentLabel.OUT_OF_SCOPE


def test_lab_write_tools_require_confirmation() -> None:
    for tool in (RequestEquipmentReservationTool(), CreateMaintenanceTicketTool()):
        assert tool.risk == ToolRisk.WRITE
        with pytest.raises(ToolPermissionError):
            assert_permitted(tool, confirmed=False)
        assert_permitted(tool, confirmed=True)


def test_reservation_request_requires_timezone_and_ordered_times() -> None:
    start = datetime.now(UTC) + timedelta(days=2)
    end = start + timedelta(hours=2)
    parsed = ReservationRequestInput(
        equipment_id="LAB-CF-01",
        start_at=start,
        end_at=end,
        purpose="样品前处理",
    )
    assert parsed.end_at > parsed.start_at

    with pytest.raises(ValidationError):
        ReservationRequestInput(
            equipment_id="LAB-CF-01",
            start_at=start.replace(tzinfo=None),
            end_at=end,
            purpose="样品前处理",
        )

    with pytest.raises(ValidationError):
        ReservationRequestInput(
            equipment_id="LAB-CF-01",
            start_at=end,
            end_at=start,
            purpose="样品前处理",
        )
