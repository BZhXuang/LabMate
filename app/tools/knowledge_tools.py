"""Knowledge retrieval tool for LabMate policies and operating guidance."""

from pydantic import BaseModel, Field

from app.core.enums import ToolRisk
from app.retrieval.hybrid import HybridRetriever
from app.schemas.agent import ToolResult
from app.tools.base import Tool, ToolContext


class KnowledgeSearchInput(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=200,
        description="实验室制度或共享仪器运维检索问题",
    )


class SearchKnowledgeTool(Tool):
    name = "search_knowledge"
    description = (
        "检索高校实验室安全、共享仪器预约和报修制度摘要，不查询真实校园设备状态。"
        "适用于培训资格、预约规则、故障上报和管理流程问题。"
        "返回带文档、章节和片段标识的证据，供回答引用。"
    )
    risk = ToolRisk.READ
    input_model = KnowledgeSearchInput

    def __init__(self, retriever: HybridRetriever) -> None:
        self._retriever = retriever

    async def execute(self, parsed: KnowledgeSearchInput, context: ToolContext) -> ToolResult:
        chunks = await self._retriever.retrieve(parsed.query, top_k=4)
        return ToolResult(
            name=self.name,
            success=True,
            output={
                "chunks": [
                    {
                        "chunk_id": chunk.chunk_id,
                        "document_id": chunk.document_id,
                        "title": chunk.title,
                        "section": chunk.section,
                        "content": chunk.content[:400],
                    }
                    for chunk in chunks
                ]
            },
        )
