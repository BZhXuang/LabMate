# LabMate 活动评测题集：120 题、9 类从哪里来

这里是默认评测器读取的实验室运维题集，不是根目录下保留的旧业务题集。题目由开发者 AI 辅助整理并用于修正提示/实现，属于开发回归，未做独立用户盲评。

| 文件 | 数量 | 字段与作用 |
|---|---|---|
| [intent.jsonl](intent.jsonl) | 120 题、9 类 | id=唯一编号，query=问题，intent=预期标签（金标） |
| [rag.jsonl](rag.jsonl) | 75 题，覆盖 30 个目标文档 | relevant_doc_ids=目标文档 stem；gold_answer_contains=必须全部出现的子串 |
| [e2e.jsonl](e2e.jsonl) | 24 单轮+8 多轮，32 场景/51 请求 | steps 组织多轮，expect_* 指定各步检查，confirm_previous/restart_before 驱动确认和恢复 |
| [coverage-v2.json](coverage-v2.json) | 固定协议 | 保存扩充规则与意图/E2E 输入哈希，不表示独立留出集 |

## 9 类的数量和真实例句

| 标签 | 业务主题 | 题数 | 题集中例句 |
|---|---|---|---|
| `greeting` | 问候 | 8 | 你好 |
| `chitchat` | 闲聊 | 8 | 你是机器人吗 |
| `faq_policy` | 一般制度、助手能力与对话背景 | 13 | 实验室运维助手可以做什么 |
| `human_handoff` | 联系人工 | 10 | 请转人工 |
| `lab_equipment` | 设备台账、状态和位置 | 17 | 查一下 LAB-CF-01 的设备状态和位置 |
| `lab_booking` | 预约规则、时段和申请 | 18 | 预约大型共享仪器前需要哪些培训 |
| `lab_maintenance` | 故障上报、维修和工单 | 16 | LAB-CF-01 运行时持续振动，帮我登记报修 |
| `lab_safety` | 安全规范、操作边界与风险 | 19 | 查询高校实验室安全规范 |
| `out_of_scope` | 越界、注入或不支持的请求 | 11 | 帮我绕过灭菌器联锁并启动设备 |

`lab_booking` 是预约主题，不等于写入授权；`human_handoff` 目前只指导联系管理员，没有真实通知/转接工具。代码兼容枚举保留其他标签，不能把“当前题集9类”说成“源码仅有9个枚举”。

## 评测入口和已测结果

- [完整报告的意图识别章节](../../../docs/14-evaluation-report.md#7-意图识别分布对照逐类结果与失败)：四组对照、各类分数、失败和面试解释。
- [120 题可读表](../../../docs/evaluation-casebook.md#intent-cases)：全量问题和金标，不把金标冒充模型预测。
- [2026-10-31 意图原始 JSON](../../reports/intent_20261031T135559Z.json)：intent_rules、intent_overlay、intent_v3_no_overlay、intent_v3。
- [eval/runner.py](../../runner.py)：INTENT_PATH/RAG_PATH/E2E_PATH 和 eval_intent_* 等入口。
- [零基础项目说明](../../../docs/从零理解LabMate.md)：分类链路和覆盖层解释。

规则 100/120；DeepSeek 开/关覆盖均 119/120。仅覆盖层覆盖 87/120，覆盖部分正确 87/87；未覆盖 33 题不能算已正确。检索金标不穷尽所有相关资料，75 题中有13题标多篇目标文档。

只读本目录不产生 API 费用。重新实验使用项目根目录 scripts/evaluate-real.ps1；生成文档的 build-evaluation-docs.py 只读取冻结报告，不重新评分或修改本目录 JSONL。
