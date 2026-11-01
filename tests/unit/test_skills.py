from app.skills.loader import match_skill


def test_match_skill_by_trigger() -> None:
    skill = match_skill("查询 LAB-CF-01 的设备状态", "faq_policy")
    assert skill is not None
    assert skill["name"] == "equipment_status"
    assert "get_lab_equipment_status" in skill["tools"]


def test_match_skill_by_intent_when_no_trigger() -> None:
    skill = match_skill("请查设备信息", "lab_booking")
    assert skill is not None
    assert skill["name"] == "equipment_booking"


def test_no_skill_for_chitchat() -> None:
    assert match_skill("今天天气真好", "chitchat") is None
