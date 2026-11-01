"""Conversation summarisation prompt."""

SUMMARY_SYSTEM = """把实验室运维对话压成简短摘要，保留：用户诉求、设备编号、时段、已查状态、待确认操作。只输出 JSON。"""

SUMMARY_USER = """历史：
{history}

输出 JSON：
{{"summary":"..."}}
"""
