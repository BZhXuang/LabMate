"""High-precision lexical overlay applied after the LLM intent classifier.

The overlay handles stable LabMate domain phrases and safety boundaries.
"""

from __future__ import annotations

import re

from app.core.enums import IntentLabel

_GREETING_ONLY = re.compile(
    r"^(你好|您好|hi|hello|早上好|哈喽|哈喽客服)(，在吗|在吗)?[!！。.~]*$",
    re.IGNORECASE,
)

_HANDOFF = ("转人工", "人工客服", "接人工", "转接", "人工审核", "值班经理")
_JAILBREAK = ("ignore previous", "jailbreak", "系统提示词")
_OOS = ("股市", "写作业", "炸弹", "总统", "医疗诊断", "炒股", "造炸弹")
_LAB_EQUIPMENT_ID = re.compile(r"\bLAB-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", re.IGNORECASE)
_LAB_MAINTENANCE = (
    "报修",
    "维修申请",
    "设备故障",
    "仪器故障",
    "异常噪音",
    "异常振动",
    "设备坏了",
    "故障工单",
    "维修工单",
)
_LAB_BOOKING = ("预约", "预约时段", "空闲时段", "可用时段", "预约流程")
_LAB_STATUS = ("设备状态", "仪器状态", "设备台账", "设备在哪", "仪器在哪", "有哪些设备")
_LAB_SAFETY = (
    "实验室安全",
    "安全规范",
    "安全制度",
    "离心机",
    "显微镜",
    "高压灭菌",
    "上机培训",
    "仪器安全",
    "设备安全",
    "操作规程",
    "操作SOP",
)
_UNSAFE_CONTROL_ACTION = re.compile(
    r"(?:绕过|屏蔽|禁用|关闭|解除|强行解锁)[^。！？\n]{0,12}"
    r"(?:联锁|报警|安全保护|防护装置|限位)|"
    r"(?:联锁|报警|安全保护|防护装置|限位)[^。！？\n]{0,12}"
    r"(?:绕过|屏蔽|禁用|关闭|解除|强行解锁)"
)
_UNSAFE_DEVICE_REQUEST = ("提高转速", "修改安全限值", "远程启动设备")


def high_precision_intent(query: str) -> IntentLabel | None:
    """Return a label only when the rule is confident; otherwise None."""
    text = query.strip()
    if not text:
        return None
    lowered = text.lower()

    if any(token in lowered for token in _JAILBREAK) or any(token in text for token in _OOS):
        return IntentLabel.OUT_OF_SCOPE
    if _UNSAFE_CONTROL_ACTION.search(text) or any(
        token in text for token in _UNSAFE_DEVICE_REQUEST
    ):
        return IntentLabel.OUT_OF_SCOPE
    if any(token in text for token in _HANDOFF):
        return IntentLabel.HUMAN_HANDOFF
    has_lab_id = bool(_LAB_EQUIPMENT_ID.search(text))
    if any(token in text for token in _LAB_MAINTENANCE):
        return IntentLabel.LAB_MAINTENANCE
    if any(token in text for token in _LAB_BOOKING):
        return IntentLabel.LAB_BOOKING
    if has_lab_id or any(token in text for token in _LAB_STATUS):
        return IntentLabel.LAB_EQUIPMENT
    if any(token in text for token in _LAB_SAFETY):
        return IntentLabel.LAB_SAFETY
    if _GREETING_ONLY.match(text) or _GREETING_ONLY.match(lowered):
        return IntentLabel.GREETING
    if (
        text in {"今天天气真好", "你是机器人吗", "讲个笑话", "你叫什么名字", "在忙什么"}
        or "吃什么" in text
    ):
        return IntentLabel.CHITCHAT
    return None


def apply_intent_overlay(query: str, label: IntentLabel) -> tuple[IntentLabel, str | None]:
    forced = high_precision_intent(query)
    if forced is None or forced == label:
        return label, None
    return forced, f"overlay:{forced.value}"
