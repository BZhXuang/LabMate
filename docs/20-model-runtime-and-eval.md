# LabMate 真实模型运行与评测复现

## 两套模型分别负责什么

`BAAI/bge-small-zh-v1.5` 将文档与查询分别编码为 512 维归一化向量；向量库按相似度召回候选。`BAAI/bge-reranker-base` 将查询和候选正文联合编码，重新判断相关性。它只重排候选，不补回未召回的文档。DeepSeek 负责意图、改写、规划、生成与证据判断，不承担这里的本地 embedding。

2026-10-31 历史测量环境安装了 `sentence-transformers==3.4.1`、`transformers==4.57.6` 和 `torch==2.15.0`，并使用 CPU。环境约束保存在根目录 `constraints-models.txt`；PyTorch 包版本可能带 `+cpu` 后缀。公开副本不包含 Python 虚拟环境和模型权重；克隆后需按下方步骤自行安装、下载，并以运行时能力接口确认当前实际后端。

## 安装、下载与离线加载

在包含 pyproject.toml 的项目目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,rerank]" -c constraints-models.txt
# 官方源连接慢时，可在 pip install 后增加：
# -i https://pypi.tuna.tsinghua.edu.cn/simple
.\.venv\Scripts\python.exe scripts/prepare_models.py --endpoint https://hf-mirror.com
```

下载脚本固定远程提交版本，只下载当前推理需要的权重、分词器和配置，并在 `data/local/models/manifest.json` 保存文件 SHA256 与版本。模型分别位于 `data/local/models/bge-small-zh-v1.5/` 和 `bge-reranker-base/`。完成下载后只更新本机 `.env` 的模型开关和路径，保留其他配置及密钥。

2026-10-31 历史测量使用的权重版本为 embedding `7999e1d3359715c523056ef9478215996d62a620`，reranker `2cfc18c9415c912f9d8155881c133215df768a70`。文件不随公开仓库发布；克隆后应执行下载脚本，并核对本机 manifest。

已有虚拟环境若引用不存在的 Python，先用有效 Python 修复或重建。当前机器的 `.venv` 已修复，常规运行直接使用其 Scripts/python.exe。

## 确认真正运行模型

```powershell
.\scripts\evaluate-real.ps1 -Task retrieval
# 完整评测会使用 .env 中的 DeepSeek 密钥并产生调用费用：
.\scripts\evaluate-real.ps1 -WithLLM
```

脚本启用真实模型，先实际编码两个文本和重排两个候选，检查维度、输出形状及后端。任一模型回退则停止。报告保存 `model_verification`、包版本、输入文件哈希与模型 manifest，避免把“配置开关为 true”当作实际加载证据。

复现脚本使用 CPU 线程数 4、关闭 tokenizer 多线程、从本地路径离线加载，E2E 使用隔离文件 SQLite，便于验证服务重建恢复，不修改开发数据库。在线 API 与运行中的其他程序仍可能影响延迟，不把这些设置当成生产压测配置。

## 对照实验的口径

检索分别运行 BM25、单独 BGE 向量、BM25+BGE+RRF、融合候选+Cross-Encoder；前三条各取五个候选，最后一条先取八个再留五个，因此不能把管线差值全部归因于重排。意图保留规则、单独覆盖层和当前提示的覆盖层开/关对照，不将旧业务提示用于实验室标签。

生成比较无上下文、单次混合检索与生成后自检。为保持历史评测协议，生成评测不额外重排，也不运行完整 MULTI 循环；E2E 才通过当前图和真实重排分支。知识库与 75 条检索/生成题不变；意图扩至 120 条，E2E 扩至 32 场景 / 51 轮，新增确认、恢复、记忆及 MULTI；扩充前后比例不作同集提升归因。

保存的历史成绩与测量日期见[实测报告](../eval/LABMATE_MEASURED.md)。报告原始源码哈希对应测量时版本；公开版裁剪后代码没有重新测出同一组真实模型指标。

## 开发启动

`scripts/dev-start.ps1` 默认尝试启用真实向量和重排；仅显式加 `-Lightweight` 才关闭。模型依赖和权重缺失时，公开副本会按配置使用回退后端。API 的 `/api/v1/capabilities` 从检索器 provider 读取实际状态；成功加载权重时应看到 `bge-small-zh-v1.5` 和 `cross-encoder`。内存缓存/向量库仍可能使 degraded 为 true，这不代表本地模型失败。

Markdown 知识库继续使用标题切分。PDF/OCR 的可选依赖、真实校园集成、多实例并发和完整多轮收益消融是独立事项，详见[实现边界](12-limitations.md)。
