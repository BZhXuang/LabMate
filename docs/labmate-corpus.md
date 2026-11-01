# LabMate 知识库清单

更新日期：2026-10-30。活动知识库共 **30 篇 Markdown**，其中 **24 篇为 AI 辅助编写的原创演示语料**，不是新增的真实高校制度文件。另有 1 份重庆大学官方 PDF 作为预约资格参考原件，不计入活动 Markdown 数量。

## 原有六篇

| 文档 | 内容与来源性质 |
|---|---|
| [高校安全与助手边界](../knowledge/labops/01-laboratory-safety-governance.md) | 公开通知发布目的摘要，加项目处理边界 |
| [大型仪器预约](../knowledge/labops/02-shared-instrument-booking.md) | 多校公开制度摘要，各自保留适用范围 |
| [故障与维修申请](../knowledge/labops/03-instrument-fault-reporting.md) | 江苏科技大学学院维修流程摘要，加演示工单说明 |
| [设备操作边界](../knowledge/labops/04-equipment-operation-boundaries.md) | 项目安全回答规则，附公开参考入口 |
| [设备台账](../knowledge/labops/05-demo-equipment-catalog.md) | 项目模拟设备、位置与状态说明 |
| [多条件问答案例](../knowledge/labops/06-labops-multi-hop-cases.md) | 项目编写案例，用于区分资料、资格和业务状态 |

公开资料的核验程度见 [来源记录](labmate-sources.md)，并非上述六篇都有对应官方原件。

## 新增二十四篇

以下全部为项目自拟，版本 `LabMate-demo-2026-10-v2`。每篇包含多个独立主题段落、边界与异常情况；可用于 RAG、跨文档问答和拒答回归。没有伪造官网链接、学校文号或制造商参数。

| 文档 | 主要问题 |
|---|---|
| [准入与角色](../knowledge/labops/demo-ops-access-and-roles.md) | 谁核验准入，课题组负责人能否代替设备管理员授权 |
| [培训与授权](../knowledge/labops/demo-ops-training-authorization.md) | 通用培训和专项培训的差别，何时需要复核 |
| [预约申请](../knowledge/labops/demo-ops-reservation-request.md) | 必填字段、用户确认与待审核的含义 |
| [取消与爽约](../knowledge/labops/demo-ops-cancellation-no-show.md) | 变更材料、原因区分、当前不支持取消工具 |
| [预约冲突](../knowledge/labops/demo-ops-booking-conflicts.md) | 时段交集、跨日时区、现场缓冲的边界 |
| [维护与开放](../knowledge/labops/demo-ops-maintenance-windows.md) | 维护中无空闲也不能预约，恢复需何种确认 |
| [故障工单字段](../knowledge/labops/demo-ops-fault-ticket-fields.md) | 事实描述、错误码原文与禁止猜测诊断 |
| [故障优先级与状态](../knowledge/labops/demo-ops-fault-priority-and-status.md) | urgent 与 open 的含义，为什么不等于派单 |
| [维修验收](../knowledge/labops/demo-ops-repair-acceptance.md) | 验收清单、遗留问题与重新使用审核 |
| [点检保养校准](../knowledge/labops/demo-ops-preventive-maintenance.md) | 三类记录的区别，不编造统一周期 |
| [耗材交接](../knowledge/labops/demo-ops-consumables-handover.md) | 领取记录、兼容性与不明标签处理 |
| [使用日志](../knowledge/labops/demo-ops-usage-logs.md) | 实际时长、离场交接与历史更正 |
| [数据导出](../knowledge/labops/demo-ops-data-export.md) | 权限范围、原始文件、保存与备份边界 |
| [样本交接](../knowledge/labops/demo-ops-sample-handover.md) | 匿名编号、数量差异、委托检测与上机的区别 |
| [费用核对](../knowledge/labops/demo-ops-billing-review.md) | 收费版本、故障异议与不承诺退款 |
| [外部访客](../knowledge/labops/demo-ops-external-visitors.md) | 参观、送样与上机三种访问许可 |
| [制度版本](../knowledge/labops/demo-ops-document-versioning.md) | 演示规则的出处、跨校冲突与更新审核 |
| [交班移交](../knowledge/labops/demo-ops-shift-handover.md) | 待办清单、责任与未知状态不补全 |
| [应急信息上报](../knowledge/labops/demo-safety-emergency-report.md) | 先保障安全，工单不等于报警 |
| [设施环境异常](../knowledge/labops/demo-safety-electrical-facilities.md) | 水电通风与设备故障分流，不操作设施 |
| [化学品信息](../knowledge/labops/demo-safety-chemical-information.md) | SDS、标签核对与未知物品处理边界 |
| [生物样本声明](../knowledge/labops/demo-safety-biosample-declaration.md) | 风险、隐私、伦理和上机许可分别核对 |
| [设备类型边界](../knowledge/labops/demo-safety-device-boundaries.md) | 离心、激光、压力类问题不推断型号参数 |
| [联合判断案例](../knowledge/labops/demo-ops-cross-topic-cases.md) | 培训加样本、维护加时段、报修加费用等组合问题 |

## 系统能力与文档的关系

可执行工具仍为设备搜索、设备状态、时段检查、待确认预约、待确认报修及知识检索。新增文档主要扩充可问的问题，没有添加培训审批、取消改期、维修状态更新、计费、导出、送样、访客或应急通知接口。回答中涉及这类流程时，需说明交管理员处理，不能假装执行成功。

本次扩库同时将检索/生成回归集从 27 条扩至 75 条：保留原题，新文档各增加两条问题。新增问题和语料均由 AI 辅助整理，属于开发回归集，不是独立真实用户测试集。扩库后的实测见 [LabMate 实测记录](../eval/LABMATE_MEASURED.md)。
