#!/usr/bin/env python3
"""Merge interview Q&A markdown files and render a Chinese PDF."""

from __future__ import annotations

import html
import os
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT_MD = DOCS / "面试问答全集.md"
OUT_PDF = ROOT / "output" / "pdf" / "面试问答全集.pdf"
TMP_PNG = ROOT / "tmp" / "pdfs"


COVER = """# LabMate · 高校共享仪器运维助手面试问答全集

> 围绕 LabMate 的业务、架构、检索、工具与评测准备。业务台账为演示数据，回答以当前代码为准。
> 当前指标以 eval/LABMATE_MEASURED.md（2026-10-31）为准；已实际加载 BGE small 与 bge-reranker-base。
> 题目与答案来源：docs/interview/labmate-question-bank.md。

## 怎么用

准备项目设计、Self-RAG、六个实验室工具、安全确认、数据来源和评测限制。先讲机制，再给例子、源码与验证证据。

## 当前数据速览

知识库 30 篇 / 108 个片段；意图 120 题；检索与生成 75 题；E2E 32 场景 / 51 轮。BM25 P@1 68.0%，真实 RRF 73.3%，Cross-Encoder 管线 78.7%；意图 119/120，E2E 32/32 场景通过，后端 185 项测试通过；候选范围和开发集偏差见原报告。
"""


def _strip_footer(text: str) -> str:
    text = re.sub(r"\n+上一章[^\n]*\n?$", "\n", text.strip())
    text = re.sub(r"\n+上一份[^\n]*\n?$", "\n", text.strip())
    return text.strip() + "\n"


def merge_markdown() -> str:
    question_bank = _strip_footer(
        (DOCS / "interview" / "labmate-question-bank.md").read_text(encoding="utf-8-sig")
    )
    bank_body = question_bank.split("\n", 1)[1].lstrip("\n")
    bank_body = re.sub(
        r"(?<=\]\()(\.\.?/[^)]+)(?=\))",
        lambda match: Path(
            os.path.relpath(DOCS / "interview" / match.group(1), OUT_MD.parent)
        ).as_posix(),
        bank_body,
    )
    return f"{COVER.strip()}\n\n---\n\n{bank_body}"


def register_fonts() -> tuple[str, str]:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light", "STSong-Light"


def make_styles(body: str, heading: str) -> dict:
    ss = getSampleStyleSheet()
    navy = colors.HexColor("#1B3A4B")
    ink = colors.HexColor("#1A1A1A")
    muted = colors.HexColor("#4A5560")
    styles = {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=ss["Title"],
            fontName=heading,
            fontSize=22,
            leading=30,
            textColor=navy,
            alignment=TA_CENTER,
            spaceAfter=12,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=ss["Normal"],
            fontName=body,
            fontSize=11,
            leading=18,
            textColor=muted,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=ss["Heading1"],
            fontName=heading,
            fontSize=16,
            leading=24,
            textColor=navy,
            spaceBefore=16,
            spaceAfter=10,
            borderPadding=4,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=ss["Heading2"],
            fontName=heading,
            fontSize=13,
            leading=20,
            textColor=navy,
            spaceBefore=14,
            spaceAfter=8,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=ss["Heading3"],
            fontName=heading,
            fontSize=11,
            leading=17,
            textColor=colors.HexColor("#2C5F7C"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            parent=ss["Normal"],
            fontName=body,
            fontSize=9.5,
            leading=15.5,
            textColor=ink,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "quote": ParagraphStyle(
            "quote",
            parent=ss["Normal"],
            fontName=body,
            fontSize=9.5,
            leading=15,
            textColor=muted,
            leftIndent=10,
            borderPadding=6,
            spaceAfter=8,
            backColor=colors.HexColor("#F4F7F8"),
        ),
        "open": ParagraphStyle(
            "open",
            parent=ss["Normal"],
            fontName=body,
            fontSize=9.5,
            leading=15.5,
            textColor=colors.HexColor("#1A4A3A"),
            backColor=colors.HexColor("#EEF7F2"),
            borderPadding=4,
            spaceAfter=6,
        ),
        "code": ParagraphStyle(
            "code",
            parent=ss["Code"],
            fontName="Courier",
            fontSize=7.5,
            leading=10.5,
            textColor=ink,
            backColor=colors.HexColor("#F6F6F4"),
            leftIndent=4,
            rightIndent=4,
            spaceAfter=8,
        ),
        "li": ParagraphStyle(
            "li",
            parent=ss["Normal"],
            fontName=body,
            fontSize=9.5,
            leading=15,
            textColor=ink,
            leftIndent=14,
            bulletIndent=4,
            spaceAfter=3,
        ),
        "th": ParagraphStyle(
            "th",
            parent=ss["Normal"],
            fontName=heading,
            fontSize=8,
            leading=12,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "td": ParagraphStyle(
            "td",
            parent=ss["Normal"],
            fontName=body,
            fontSize=8,
            leading=12,
            textColor=ink,
            alignment=TA_LEFT,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=ss["Normal"],
            fontName=body,
            fontSize=8,
            textColor=muted,
            alignment=TA_CENTER,
        ),
    }
    return styles


_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def inline_to_xml(text: str) -> str:
    text = text.replace("\t", "    ")
    text = html.escape(text)
    text = _LINK.sub(r"\1", text)
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _INLINE_CODE.sub(r'<font face="Courier" size="8">\1</font>', text)
    return text


def split_table_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def is_table_sep(line: str) -> bool:
    s = line.strip().replace(" ", "")
    return bool(s) and set(s) <= set("|:-") and "-" in s


def parse_md(md: str, styles: dict) -> list:
    story: list = []
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    n = len(lines)
    first_h1 = True

    def para(text: str, style: str):
        if not text.strip():
            return
        story.append(Paragraph(inline_to_xml(text.strip()), styles[style]))

    while i < n:
        line = lines[i]
        if line.strip() == "```" or line.strip().startswith("```"):
            buf = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i].replace("\t", "    "))
                i += 1
            i += 1
            code = "\n".join(buf) if buf else ""
            if len(code) > 2500:
                code = code[:2500] + "\n... (truncated)"
            block = Preformatted(code or " ", styles["code"])
            story.append(KeepTogether([block]))
            continue

        if (
            line.strip().startswith("|")
            and i + 1 < n
            and (lines[i + 1].strip().startswith("|") or is_table_sep(lines[i + 1]))
        ):
            rows = [split_table_row(line)]
            i += 1
            if i < n and is_table_sep(lines[i]):
                i += 1
            while i < n and lines[i].strip().startswith("|") and not is_table_sep(lines[i]):
                rows.append(split_table_row(lines[i]))
                i += 1
            if not rows:
                continue
            ncol = max(len(r) for r in rows)
            norm = [r + [""] * (ncol - len(r)) for r in rows]
            usable = A4[0] - 36 * mm
            col_w = usable / ncol
            data = []
            for ri, row in enumerate(norm):
                st = styles["th"] if ri == 0 else styles["td"]
                data.append([Paragraph(inline_to_xml(c), st) for c in row])
            tbl = Table(data, colWidths=[col_w] * ncol, repeatRows=1)
            tbl.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B3A4B")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FAFBFC")),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#F4F7F8")],
                        ),
                        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D7DE")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(tbl)
            story.append(Spacer(1, 8))
            continue

        stripped = line.strip()
        if stripped == "---":
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#D0D7DE")))
            story.append(Spacer(1, 8))
            i += 1
            continue

        if stripped.startswith("# "):
            title = stripped[2:].strip()
            if not first_h1:
                story.append(PageBreak())
            first_h1 = False
            story.append(Paragraph(inline_to_xml(title), styles["h1"]))
            i += 1
            continue
        if stripped.startswith("## "):
            story.append(Paragraph(inline_to_xml(stripped[3:].strip()), styles["h2"]))
            i += 1
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(inline_to_xml(stripped[4:].strip()), styles["h3"]))
            i += 1
            continue

        if stripped.startswith("> "):
            buf = [stripped[2:]]
            i += 1
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            para(" ".join(buf), "quote")
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            while i < n and (
                lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")
            ):
                item = lines[i].strip()[2:]
                story.append(Paragraph("• " + inline_to_xml(item), styles["li"]))
                i += 1
            story.append(Spacer(1, 4))
            continue

        if re.match(r"^\d+\.\s+", stripped):
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                item = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                story.append(Paragraph(inline_to_xml(item), styles["li"]))
                i += 1
            story.append(Spacer(1, 4))
            continue

        if not stripped:
            i += 1
            continue

        buf = [stripped]
        i += 1
        while i < n:
            nxt = lines[i]
            if not nxt.strip():
                break
            if nxt.strip().startswith(("#", "-", "*", ">", "|", "```")) or nxt.strip() == "---":
                break
            if re.match(r"^\d+\.\s+", nxt.strip()):
                break
            buf.append(nxt.strip())
            i += 1
        text = " ".join(buf)
        style = "open" if text.startswith("**开口：**") or text.startswith("开口：") else "body"
        para(text, style)

    return story


def add_page_decor(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#1B3A4B"))
    canvas.rect(0, A4[1] - 8 * mm, A4[0], 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("STSong-Light", 8)
    canvas.drawString(18 * mm, A4[1] - 5.5 * mm, "LabMate 面试问答全集")
    canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 5.5 * mm, "对照仓库 · 勿背简历未落地能力")
    canvas.setFillColor(colors.HexColor("#F4F7F8"))
    canvas.rect(0, 0, A4[0], 12 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#4A5560"))
    canvas.setFont("STSong-Light", 8)
    canvas.drawCentredString(A4[0] / 2, 5 * mm, f"{doc.page}")
    canvas.restoreState()


def build_pdf(md: str) -> None:
    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    body, heading = register_fonts()
    styles = make_styles(body, heading)
    doc = SimpleDocTemplate(
        str(OUT_PDF),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title="LabMate 面试问答全集",
        author="LabMate",
    )
    story = parse_md(md, styles)
    doc.build(story, onFirstPage=add_page_decor, onLaterPages=add_page_decor)


def main() -> int:
    md = merge_markdown()
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"wrote {OUT_MD} ({len(md.splitlines())} lines)")
    build_pdf(md)
    print(f"wrote {OUT_PDF} ({OUT_PDF.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
