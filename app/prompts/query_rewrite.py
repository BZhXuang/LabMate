"""Query rewrite prompt."""

REWRITE_SYSTEM = """你改写高校实验室运维检索查询。只输出 JSON。
生成 1-3 条更适合检索的短查询，保留关键约束（设备型号/编号、预约时段、培训资格、故障现象和安全边界）。
"""

REWRITE_USER = """原始问题：{query}
仍缺少的信息：{missing_aspect}

输出 JSON：
{{"queries":["..."]}}
"""
