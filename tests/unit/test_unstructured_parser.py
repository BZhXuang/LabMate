from pathlib import Path
from types import SimpleNamespace

from app.config.settings import Settings
from app.core.enums import DocumentCategory
from app.retrieval.chunking import chunk_markdown, stable_chunk_id
from app.retrieval.unstructured_parser import (
    ParsedElement,
    elements_to_chunks,
    list_knowledge_files,
    parse_path,
)

FIXTURE_HTML = Path("tests/fixtures/docs/policy.html")


class _FakeElement:
    def __init__(
        self,
        category: str,
        text: str,
        *,
        page_number: int | None = None,
        table_html: str | None = None,
    ) -> None:
        self.category = category
        self.text = text
        self.metadata = SimpleNamespace(page_number=page_number, text_as_html=table_html)


def _settings(**overrides) -> Settings:
    data = {
        "app_env": "testing",
        "unstructured_enabled": True,
        "unstructured_force": False,
    }
    data.update(overrides)
    return Settings(**data)


def test_title_becomes_section_and_table_stays_whole() -> None:
    elements = [
        _FakeElement("Header", "公司页眉"),
        _FakeElement("Title", "设备预约规则", page_number=1),
        _FakeElement("NarrativeText", "大型仪器使用前须完成对应培训。", page_number=1),
        _FakeElement(
            "Table",
            "申请时段 设备编号\n冲突处理 联系管理员",
            page_number=2,
            table_html="<table><tr><td>设备编号</td></tr></table>",
        ),
        _FakeElement("Footer", "页脚"),
        _FakeElement("PageBreak", ""),
    ]
    chunks = elements_to_chunks(
        elements,
        document_id="booking_policy",
        title="booking_policy",
        category=DocumentCategory.LAB_OPERATIONS,
        source="policy.pdf",
    )
    assert [c.section for c in chunks] == ["设备预约规则", "设备预约规则"]
    assert chunks[0].metadata["element_type"] == "NarrativeText"
    assert chunks[1].metadata["element_type"] == "Table"
    assert chunks[1].metadata["table_html"].startswith("<table>")
    assert chunks[1].metadata["page_number"] == "2"
    assert chunks[1].metadata["parser"] == "unstructured"
    assert "联系管理员" in chunks[1].content


def test_table_is_not_windowed() -> None:
    body = "设备预约表格规则。" * 100
    assert len(body) > 500
    chunks = elements_to_chunks(
        [_FakeElement("Table", body, table_html="<table><tr><td>x</td></tr></table>")],
        document_id="equipment_schedule",
        title="equipment_schedule",
        category=DocumentCategory.LAB_OPERATIONS,
        source="t.pdf",
    )
    assert len(chunks) == 1
    assert chunks[0].metadata["element_type"] == "Table"
    assert chunks[0].content == body
    elements = [
        ParsedElement(category="Image", text=""),
        ParsedElement(category="Image", text="  设备面板照片说明  ", page_number="3"),
        ParsedElement(category="ListItem", text="检查设备外观并记录异常。"),
    ]
    chunks = elements_to_chunks(
        elements,
        document_id="equipment_schedule",
        title="equipment_schedule",
        category=DocumentCategory.LAB_OPERATIONS,
        source="photo.png",
    )
    assert len(chunks) == 2
    assert chunks[0].metadata["element_type"] == "Image"
    assert "设备面板" in chunks[0].content
    assert chunks[1].metadata["element_type"] == "ListItem"


def test_unstructured_chunk_ids_are_stable() -> None:
    elements = [
        _FakeElement("Title", "A"),
        _FakeElement("NarrativeText", "hello world"),
        _FakeElement("Title", "B"),
        _FakeElement("NarrativeText", "second section about administrator approval"),
    ]
    once = elements_to_chunks(
        elements,
        document_id="booking_policy",
        title="t",
        category=DocumentCategory.LAB_OPERATIONS,
        source="x",
    )
    twice = elements_to_chunks(
        elements,
        document_id="booking_policy",
        title="t",
        category=DocumentCategory.LAB_OPERATIONS,
        source="x",
    )
    assert [c.chunk_id for c in once] == [c.chunk_id for c in twice]
    assert once[0].chunk_id == stable_chunk_id("booking_policy", 0)


def test_parse_path_uses_injected_partition(tmp_path: Path) -> None:
    path = tmp_path / "booking_policy.pdf"
    path.write_bytes(b"%PDF-fake")

    def fake_partition(_path: Path) -> list[_FakeElement]:
        return [
            _FakeElement("Title", "预约"),
            _FakeElement("NarrativeText", "使用设备前须完成培训。"),
        ]

    chunks = parse_path(
        path,
        document_id="doc",
        title="booking_policy",
        category=DocumentCategory.LAB_OPERATIONS,
        settings=_settings(),
        partition_fn=fake_partition,
    )
    assert len(chunks) == 1
    assert chunks[0].section == "预约"
    assert chunks[0].metadata["parser"] == "unstructured"


def test_parse_path_skips_non_markdown_without_unstructured(tmp_path: Path) -> None:
    path = tmp_path / "scan.png"
    path.write_bytes(b"\x89PNG")
    chunks = parse_path(
        path,
        document_id="scan",
        title="scan",
        category=DocumentCategory.FAQ,
        settings=_settings(),
    )
    assert chunks == []


def test_parse_path_falls_back_to_markdown(tmp_path: Path) -> None:
    path = tmp_path / "booking_policy.md"
    path.write_text("## 预约\n\n使用设备前须完成培训。\n", encoding="utf-8")
    chunks = parse_path(
        path,
        document_id="doc",
        title="booking_policy",
        category=DocumentCategory.LAB_OPERATIONS,
        settings=_settings(),
    )
    assert chunks
    assert chunks[0].section == "预约"
    assert chunks[0].metadata["parser"] == "markdown"


def test_parse_path_partition_error_falls_back_markdown(tmp_path: Path) -> None:
    path = tmp_path / "faq.md"
    path.write_text("# FAQ\n\n设备预约流程请联系管理员确认。\n", encoding="utf-8")

    def boom(_path: Path) -> list[_FakeElement]:
        raise RuntimeError("ocr crashed")

    chunks = parse_path(
        path,
        document_id="faq",
        title="faq",
        category=DocumentCategory.FAQ,
        settings=_settings(),
        partition_fn=boom,
    )
    assert chunks
    assert chunks[0].metadata["parser"] == "markdown"


def test_html_fixture_with_injected_partition() -> None:
    assert FIXTURE_HTML.is_file()

    def fake_partition(_path: Path) -> list[_FakeElement]:
        return [
            _FakeElement("Title", "实验室管理规则"),
            _FakeElement("NarrativeText", "大型仪器使用前须完成对应培训。"),
            _FakeElement(
                "Table",
                "预约设备 时段冲突 联系管理员",
                table_html="<table><tr><td>联系管理员</td></tr></table>",
            ),
        ]

    chunks = parse_path(
        FIXTURE_HTML,
        document_id="policy",
        title="lab_policy",
        category=DocumentCategory.LAB_OPERATIONS,
        settings=_settings(),
        partition_fn=fake_partition,
    )
    assert len(chunks) == 2
    assert chunks[1].metadata["element_type"] == "Table"


def test_list_knowledge_files_includes_supported_suffixes(tmp_path: Path) -> None:
    (tmp_path / "booking_policy.md").write_text("# a\n", encoding="utf-8")
    (tmp_path / "equipment.pdf").write_bytes(b"%PDF")
    (tmp_path / "ignore.txt").write_text("nope", encoding="utf-8")
    (tmp_path / ".hidden.md").write_text("# hidden\n", encoding="utf-8")
    files = list_knowledge_files(tmp_path)
    names = {path.name for path in files}
    assert names == {"booking_policy.md", "equipment.pdf"}


def test_markdown_fallback_chunk_ids_still_stable() -> None:
    text = "## A\n\n设备状态\n\n## B\n\n预约需要培训"
    once = chunk_markdown(
        text,
        document_id="booking_policy",
        title="t",
        category=DocumentCategory.LAB_OPERATIONS,
        source="x",
    )
    twice = chunk_markdown(
        text,
        document_id="booking_policy",
        title="t",
        category=DocumentCategory.LAB_OPERATIONS,
        source="x",
    )
    assert [c.chunk_id for c in once] == [c.chunk_id for c in twice]
