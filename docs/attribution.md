# 第三方代码与许可记录

LabMate 使用开源组件与参考代码。本文件集中记录代码来源；产品介绍、技术手册和面试资料按 LabMate 的实际结构描述功能。

| 来源 | 使用范围 | 许可/处理 |
|---|---|---|
| [JEen-wang/Adaptive-rag](https://github.com/JEen-wang/Adaptive-rag) | 初始工程结构及通用 RAG、状态图、工具和会话实现 | 保留根目录 [MIT LICENSE](../LICENSE) 中原版权和许可文本 |
| FastAPI、LangGraph、SQLAlchemy 等 | Web 服务、工作流和异步持久化依赖 | 具体版本与依赖见 `pyproject.toml` / `uv.lock`，各组件适用各自许可 |

组件与参考代码按各自许可使用，复制或发布时保留原版权及许可文本。公开制度、整理摘要和演示语料的来源另见 [资料核验记录](labmate-sources.md)。已有历史评测不作为当前 LabMate 结果。
