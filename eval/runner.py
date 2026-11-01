"""Offline eval harness for resume-quantifiable metrics.

python -m eval.runner --task all --llm
python -m eval.runner --task intent --llm
python -m eval.runner --task retrieval
python -m eval.runner --task generation --llm
python -m eval.runner --task e2e --llm
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.metrics import (
    accuracy,
    classification_report,
    hit_at_k,
    mrr,
    precision_at_k,
    recall_at_k,
)

ROOT = Path(__file__).resolve().parents[1]
INTENT_PATH = ROOT / "eval/dataset/labmate/intent.jsonl"
RAG_PATH = ROOT / "eval/dataset/labmate/rag.jsonl"
E2E_PATH = ROOT / "eval/dataset/labmate/e2e.jsonl"
REPORT_DIR = ROOT / "eval/reports"


def evaluation_environment() -> dict:
    """Record reproducibility details without serializing settings or secrets."""
    from app.config.settings import get_settings

    settings = get_settings()
    paths = [INTENT_PATH, RAG_PATH, E2E_PATH, INTENT_PATH.parent / "coverage-v2.json"]
    paths.extend(sorted(Path(active_knowledge_dir(settings)).rglob("*.md")))
    packages = {}
    for name in ("torch", "sentence-transformers", "transformers", "numpy", "scikit-learn"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not-installed"
    manifest = ROOT / "data/local/models/manifest.json"
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
        "llm_model": settings.deepseek_model,
        "knowledge_dir": settings.knowledge_dir,
        "input_sha256": {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        },
        "model_snapshots": json.loads(manifest.read_text(encoding="utf-8"))
        if manifest.exists()
        else None,
        "code_sha256": {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(
                [
                    *ROOT.joinpath("app").rglob("*.py"),
                    ROOT / "eval/runner.py",
                    ROOT / "eval/workflows.py",
                    ROOT / "eval/metrics.py",
                ]
            )
        },
    }


async def verify_real_models() -> dict:
    """Fail before paid evaluation if either real model cannot run inference."""
    from app.config.settings import get_settings
    from app.providers.embeddings import build_embedding_provider
    from app.providers.reranker import CrossEncoderRerankProvider

    settings = get_settings()
    embedder = build_embedding_provider(settings)
    reranker = CrossEncoderRerankProvider(settings)
    if getattr(embedder, "backend", "hash") == "hash" or not reranker.available:
        raise RuntimeError(
            f"Real models required; embedding={embedder.backend}, reranker={reranker.backend}"
        )
    vectors = await embedder.embed(["共享仪器预约", "设备故障报修"])
    scores = await reranker.rerank(
        "预约前需要培训吗", ["预约前须完成上机培训。", "设备位于二楼。"], top_n=2
    )
    if len(vectors) != 2 or len(vectors[0]) != settings.embedding_dim or len(scores) != 2:
        raise RuntimeError("Real model inference returned an unexpected shape")
    return {
        "dense_backend": embedder.backend,
        "embedding_dim": len(vectors[0]),
        "reranker_backend": reranker.backend,
        "embedding_device": str(getattr(getattr(embedder, "_model", None), "device", "unknown")),
        "reranker_device": str(getattr(getattr(reranker, "_model", None), "device", "unknown")),
        "inference_passed": True,
    }


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def active_knowledge_dir(settings) -> str:
    path = Path(settings.knowledge_dir)
    if not path.is_absolute():
        path = ROOT / path
    return str(path)


def _doc_stem(document_id: str) -> str:
    return document_id.rsplit("_", 1)[0]


def _unique_stems(chunks) -> list[str]:
    stems: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        stem = _doc_stem(chunk.document_id)
        if stem not in seen:
            seen.add(stem)
            stems.append(stem)
    return stems


def _summarize_scores(values: list[float]) -> dict:
    if not values:
        return {"mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": round(sum(values) / len(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _keyword_hit(answer: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    return all(word in answer for word in keywords)


def eval_intent_rules() -> dict:
    from app.agents.nodes.intent import rule_based_intent

    rows = load_jsonl(INTENT_PATH)
    pairs = [(row["intent"], rule_based_intent(row["query"]).label.value) for row in rows]
    return {
        "backend": "rules",
        "prompt_version": "intent_rules_v1",
        "n": len(pairs),
        "accuracy": round(accuracy(pairs), 4),
        "per_label": {k: round(v, 4) for k, v in classification_report(pairs).items()},
    }


async def eval_intent_llm(*, version: str, overlay: bool) -> dict:
    from app.agents.nodes.intent import IntentClassifier
    from app.config.settings import get_settings
    from app.prompts.intent import INTENT_SYSTEM
    from app.providers.deepseek import DeepSeekProvider

    settings = get_settings()
    if not settings.llm_configured:
        raise SystemExit("DEEPSEEK_API_KEY missing")
    if version != "intent_v3":
        raise ValueError("LabMate evaluation only supports the current intent_v3 prompt")
    llm = DeepSeekProvider(settings)
    classifier = IntentClassifier(
        llm,
        system_prompt=INTENT_SYSTEM,
        prompt_version=version,
        apply_overlay=overlay,
    )
    rows = load_jsonl(INTENT_PATH)
    semaphore = asyncio.Semaphore(4)
    errors = 0
    rule_fallbacks = 0

    async def _one(row: dict) -> tuple[str, str]:
        nonlocal errors, rule_fallbacks
        async with semaphore:
            try:
                result = await classifier.classify(row["query"])
                if result.prompt_version.startswith("intent_rules"):
                    rule_fallbacks += 1
                return row["intent"], result.label.value
            except Exception:
                errors += 1
                return row["intent"], "ERROR"

    try:
        pairs = list(await asyncio.gather(*[_one(row) for row in rows]))
    finally:
        await llm.aclose()
    mismatches = [
        {"query": rows[i]["query"], "gold": gold, "pred": pred}
        for i, (gold, pred) in enumerate(pairs)
        if gold != pred
    ]
    return {
        "backend": "deepseek",
        "prompt_version": version,
        "overlay": overlay,
        "n": len(pairs),
        "errors": errors,
        "rule_fallbacks": rule_fallbacks,
        "accuracy": round(accuracy(pairs), 4),
        "per_label": {k: round(v, 4) for k, v in classification_report(pairs).items()},
        "mismatches": mismatches,
    }


def eval_intent_overlay() -> dict:
    from app.agents.nodes.intent_overlay import high_precision_intent

    rows = load_jsonl(INTENT_PATH)
    covered_pairs = []
    uncovered = 0
    for row in rows:
        pred = high_precision_intent(row["query"])
        if pred is None:
            uncovered += 1
        else:
            covered_pairs.append((row["intent"], pred.value))
    return {
        "backend": "overlay",
        "prompt_version": "intent_overlay_v1",
        "n": len(rows),
        "uncovered": uncovered,
        "coverage": round((len(rows) - uncovered) / len(rows), 4) if rows else 0.0,
        "precision_when_covered": round(accuracy(covered_pairs), 4),
        "covered_per_label": {
            k: round(v, 4) for k, v in classification_report(covered_pairs).items()
        },
    }


async def eval_retrieval() -> dict:
    from app.config.settings import get_settings
    from app.providers.embeddings import build_embedding_provider
    from app.providers.reranker import CrossEncoderRerankProvider, LexicalRerankProvider
    from app.retrieval.hybrid import HybridRetriever
    from app.retrieval.ingest import ingest_to_memory
    from app.retrieval.reranker import DocumentReranker
    from app.retrieval.vector import VectorRetriever

    settings = get_settings()
    embedder = build_embedding_provider(settings)
    dense_backend = getattr(embedder, "backend", "vector")
    vector_label = "hash-vector" if dense_backend == "hash" else dense_backend
    hybrid_label = f"bm25+{vector_label}+rrf"
    bm25, store, _ = await ingest_to_memory(active_knowledge_dir(settings), embedder)
    vector = VectorRetriever(store, embedder)
    hybrid = HybridRetriever(bm25, vector, rrf_k=60)
    rows = load_jsonl(RAG_PATH)

    async def _run(name: str, retrieve) -> dict:
        precs1, recalls3, hits1, hits3, mrrs = [], [], [], [], []
        cases = []
        for row in rows:
            chunks = await retrieve(row["query"])
            stems = _unique_stems(chunks)
            relevant = set(row["relevant_doc_ids"])
            precs1.append(precision_at_k(relevant, stems, 1))
            recalls3.append(recall_at_k(relevant, stems, 3))
            hits1.append(hit_at_k(relevant, stems, 1))
            hits3.append(hit_at_k(relevant, stems, 3))
            mrrs.append(mrr(relevant, stems))
            cases.append({"id": row["id"], "relevant": sorted(relevant), "retrieved": stems})
        return {
            "backend": name,
            "n": len(rows),
            "precision_at_1": _summarize_scores(precs1),
            "recall_at_3": _summarize_scores(recalls3),
            "hit_at_1": _summarize_scores(hits1),
            "hit_at_3": _summarize_scores(hits3),
            "mrr": _summarize_scores(mrrs),
            "cases": cases,
        }

    async def _bm25(query: str):
        return bm25.search(query, top_k=5)

    async def _vector(query: str):
        return await vector.search(query, top_k=5)

    async def _hybrid(query: str):
        return await hybrid.retrieve(query, top_k=5)

    systems = [
        await _run("bm25", _bm25),
        await _run(vector_label, _vector),
        await _run(hybrid_label, _hybrid),
    ]
    ce_provider = CrossEncoderRerankProvider(settings)
    if ce_provider.available:
        reranker = DocumentReranker(ce_provider)

        async def _hybrid_cross_encoder(query: str):
            fused = await hybrid.retrieve(query, top_k=8)
            return await reranker.rerank(query, fused, top_n=5)

        systems.append(await _run("hybrid+cross-encoder", _hybrid_cross_encoder))
        note = (
            f"Rerank is local Cross-Encoder ({settings.cross_encoder_model}). "
            f"Dense side is {vector_label}."
        )
    else:
        fallback = DocumentReranker(LexicalRerankProvider())

        async def _hybrid_lexical(query: str):
            fused = await hybrid.retrieve(query, top_k=8)
            return await fallback.rerank(query, fused, top_n=5)

        systems.append(await _run("hybrid+lexical-fallback", _hybrid_lexical))
        # Kept out of the f-string on purpose: a backslash inside an f-string
        # expression is a SyntaxError on Python 3.11 (PEP 701 landed in 3.12).
        rerank_hint = ce_provider.load_error or 'pip install -e ".[rerank]"'
        note = (
            "Cross-Encoder not loaded; hybrid+cross-encoder skipped. "
            f"{rerank_hint}. "
            "Lexical fallback is CI-only, not a Cross-Encoder."
        )
    return {
        "n": len(rows),
        "dense_backend": vector_label,
        "local_embedding_configured": settings.local_embedding_configured,
        "cross_encoder_configured": settings.cross_encoder_configured,
        "cross_encoder_available": ce_provider.available,
        "cross_encoder_model": settings.cross_encoder_model,
        "embedding_model": settings.local_embedding_model,
        "candidate_policy": {"bm25_dense_rrf": 5, "rerank_candidates": 8, "rerank_keep": 5},
        "note": note,
        "systems": systems,
    }


async def _generate_answer(llm, query: str, evidence: str) -> str:
    from app.agents.nodes.generate import AnswerPayload
    from app.prompts.answer import ANSWER_SYSTEM, ANSWER_USER
    from app.providers.json_parser import parse_model

    response = await llm.generate(
        [
            {"role": "system", "content": ANSWER_SYSTEM},
            {
                "role": "user",
                "content": ANSWER_USER.format(
                    query=query,
                    resolved_query=query,
                    history="(无历史)",
                    intent="faq_policy",
                    strategy="single",
                    evidence=evidence,
                    tool_results="(无)",
                ),
            },
        ],
        temperature=0.0,
        max_tokens=900,
        response_format={"type": "json_object"},
    )
    return parse_model(response.content, AnswerPayload).answer


async def eval_generation() -> dict:
    from app.config.settings import get_settings
    from app.guardrails.hallucination import FaithfulnessChecker
    from app.providers.deepseek import DeepSeekProvider
    from app.providers.embeddings import build_embedding_provider
    from app.retrieval.hybrid import HybridRetriever
    from app.retrieval.ingest import ingest_to_memory
    from app.retrieval.vector import VectorRetriever

    settings = get_settings()
    if not settings.llm_configured:
        raise SystemExit("DEEPSEEK_API_KEY missing")
    llm = DeepSeekProvider(settings)
    checker = FaithfulnessChecker(llm)
    embedder = build_embedding_provider(settings)
    bm25, store, _ = await ingest_to_memory(active_knowledge_dir(settings), embedder)
    retriever = HybridRetriever(bm25, VectorRetriever(store, embedder), rrf_k=60)
    rows = load_jsonl(RAG_PATH)
    semaphore = asyncio.Semaphore(3)

    naive_supported = 0
    rag_supported = 0
    checked_supported = 0
    naive_keyword = 0
    rag_keyword = 0
    checked_keyword = 0
    naive_hallucinated = 0
    rag_hallucinated = 0
    checked_hallucinated = 0
    checker_failures = {"naive": 0, "rag": 0, "self_check": 0}
    case_details = {}

    async def _one(row: dict) -> None:
        nonlocal naive_supported, rag_supported, checked_supported
        nonlocal naive_keyword, rag_keyword, checked_keyword
        nonlocal naive_hallucinated, rag_hallucinated, checked_hallucinated
        async with semaphore:
            chunks = await retriever.retrieve(row["query"], top_k=5)
            evidence = (
                "\n\n".join(f"[{c.chunk_id}] {c.content}" for c in chunks[:6]) or "(无检索结果)"
            )
            naive = await _generate_answer(llm, row["query"], "(无检索结果)")
            rag = await _generate_answer(llm, row["query"], evidence)
            naive_judge = await checker.check(
                query=row["query"], answer=naive, chunks=chunks, tool_results_text=""
            )
            rag_judge = await checker.check(
                query=row["query"], answer=rag, chunks=chunks, tool_results_text=""
            )
            checked = rag
            checked_judge = rag_judge
            if not rag_judge.supported:
                from app.agents.nodes.faithfulness import self_correct_answer

                checked, checked_judge, _ = await self_correct_answer(
                    llm=llm,
                    checker=checker,
                    query=row["query"],
                    answer=rag,
                    chunks=chunks,
                    tool_results_text="",
                    first_result=rag_judge,
                )
            keywords = row.get("gold_answer_contains") or []
            for path, judged in (
                ("naive", naive_judge),
                ("rag", rag_judge),
                ("self_check", checked_judge),
            ):
                if judged.rationale == "checker_unavailable":
                    checker_failures[path] += 1
            if naive_judge.supported:
                naive_supported += 1
            else:
                naive_hallucinated += 1
            if rag_judge.supported:
                rag_supported += 1
            else:
                rag_hallucinated += 1
            if checked_judge.supported:
                checked_supported += 1
            else:
                checked_hallucinated += 1
            if _keyword_hit(naive, keywords):
                naive_keyword += 1
            if _keyword_hit(rag, keywords):
                rag_keyword += 1
            if _keyword_hit(checked, keywords):
                checked_keyword += 1
            case_details[row["id"]] = {
                "id": row["id"],
                "query": row["query"],
                "retrieved_doc_ids": _unique_stems(chunks),
                "naive_answer": naive,
                "rag_answer": rag,
                "checked_answer": checked,
                "rag_supported": rag_judge.supported,
                "checked_supported": checked_judge.supported,
                "rag_keyword_hit": _keyword_hit(rag, keywords),
                "checked_keyword_hit": _keyword_hit(checked, keywords),
            }
            if len(case_details) % 10 == 0 or len(case_details) == len(rows):
                print(
                    f"Generation completed {len(case_details)}/{len(rows)}",
                    file=sys.stderr,
                    flush=True,
                )

    outcomes = await asyncio.gather(*[_one(row) for row in rows], return_exceptions=True)
    failures = [
        {
            "id": rows[index]["id"],
            "error_type": type(outcome).__name__,
        }
        for index, outcome in enumerate(outcomes)
        if isinstance(outcome, BaseException)
    ]
    await llm.aclose()
    n = len(rows) - len(failures)
    if not n:
        return {
            "n": 0,
            "attempted": len(rows),
            "completed": 0,
            "completion_rate": 0.0,
            "failures": failures,
            "note": "No complete generation cases; no quality metrics are available.",
        }
    naive_h = naive_hallucinated / n
    checked_h = checked_hallucinated / n
    drop = ((naive_h - checked_h) / naive_h) if naive_h else 0.0
    return {
        "n": n,
        "attempted": len(rows),
        "completed": n,
        "completion_rate": round(n / len(rows), 4),
        "failures": failures,
        "checker_failures": checker_failures,
        "dense_backend": getattr(embedder, "backend", "unknown"),
        "retrieval_pipeline": "hybrid-rrf top_k=5, no rerank; same as historical generation protocol",
        "cases": [case_details[row["id"]] for row in rows if row["id"] in case_details],
        "judge": "deepseek-faithfulness_v1",
        "naive_no_context": {
            "faithfulness": round(naive_supported / n, 4),
            "hallucination_rate": round(naive_h, 4),
            "keyword_hit": round(naive_keyword / n, 4),
        },
        "rag": {
            "faithfulness": round(rag_supported / n, 4),
            "hallucination_rate": round(rag_hallucinated / n, 4),
            "keyword_hit": round(rag_keyword / n, 4),
        },
        "rag_plus_self_check": {
            "faithfulness": round(checked_supported / n, 4),
            "hallucination_rate": round(checked_h, 4),
            "keyword_hit": round(checked_keyword / n, 4),
        },
        "hallucination_relative_drop": round(drop, 4),
        "note": "Quality metrics use completed cases only; inspect completion_rate and failures. Unsupported includes checker failure. Same-model judge, not independent verification.",
    }


async def eval_e2e() -> dict:
    from eval.workflows import evaluate_workflows

    return await evaluate_workflows(load_jsonl(E2E_PATH))


def _resume_bullets(report: dict) -> list[str]:
    bullets = []
    intent_rules = report.get("intent_rules")
    intent_v1 = report.get("intent_v1")
    intent_v2 = report.get("intent_v2")
    intent_v3 = report.get("intent_v3")
    overlay = report.get("intent_overlay")
    if intent_v3:
        parts = [f"intent_v3+overlay {intent_v3['accuracy']:.1%}"]
        if intent_v2:
            parts.insert(0, f"intent_v2 {intent_v2['accuracy']:.1%}")
        if intent_v1:
            parts.insert(0, f"intent_v1 {intent_v1['accuracy']:.1%}")
        extra = f"；规则 {intent_rules['accuracy']:.1%}" if intent_rules else ""
        if overlay:
            extra += (
                f"；覆盖层覆盖率 {overlay['coverage']:.1%}，"
                f"命中样本准确率 {overlay['precision_when_covered']:.1%}"
            )
        bullets.append(f"意图识别：{intent_v3['n']} 条 " + " → ".join(parts) + extra)
    elif intent_rules:
        bullets.append(
            f"规则意图识别：{intent_rules['n']} 条，准确率 {intent_rules['accuracy']:.1%}"
        )
        if overlay:
            bullets.append(
                f"高精度覆盖层：覆盖 {overlay['coverage']:.1%}，"
                f"已覆盖样本准确率 {overlay['precision_when_covered']:.1%}"
            )
    retrieval = report.get("retrieval")
    if retrieval:
        bm25 = next((s for s in retrieval["systems"] if s["backend"] == "bm25"), None)
        dense = next(
            (
                s
                for s in retrieval["systems"]
                if s["backend"] not in {"bm25", "hybrid+cross-encoder", "hybrid+lexical-fallback"}
                and not str(s["backend"]).endswith("+rrf")
            ),
            None,
        )
        hybrid_rrf = next((s for s in retrieval["systems"] if s["backend"].endswith("+rrf")), None)
        cross_encoder = next(
            (s for s in retrieval["systems"] if s["backend"] == "hybrid+cross-encoder"), None
        )
        if bm25:
            bullets.append(
                f"BM25 Precision@1 {bm25['precision_at_1']['mean']:.1%}，Recall@3 {bm25['recall_at_3']['mean']:.1%}，MRR {bm25['mrr']['mean']:.2f}"
            )
        if dense:
            bullets.append(
                f"{dense['backend']} Precision@1 {dense['precision_at_1']['mean']:.1%}，"
                f"Recall@3 {dense['recall_at_3']['mean']:.1%}"
            )
        if hybrid_rrf:
            bullets.append(
                f"{hybrid_rrf['backend']} Precision@1 {hybrid_rrf['precision_at_1']['mean']:.1%}，"
                f"Recall@3 {hybrid_rrf['recall_at_3']['mean']:.1%}"
            )
        if cross_encoder:
            bullets.append(
                f"Hybrid+Cross-Encoder Precision@1 {cross_encoder['precision_at_1']['mean']:.1%}，"
                f"Recall@3 {cross_encoder['recall_at_3']['mean']:.1%}"
            )
    gen = report.get("generation")
    if gen and gen.get("naive_no_context"):
        naive = gen["naive_no_context"]
        rag = gen["rag"]
        checked = gen["rag_plus_self_check"]
        if any(gen.get("checker_failures", {}).values()):
            bullets.append(
                f"裁判忠实度：无检索 {naive['faithfulness']:.2%} → RAG {rag['faithfulness']:.2%} → RAG+自检 {checked['faithfulness']:.2%}"
            )
            bullets.append(
                f"裁判不支持率（含裁判不可用）：无检索 {naive['hallucination_rate']:.2%} → RAG+自检 {checked['hallucination_rate']:.2%}；"
                "存在裁判不可用，不能据此推断真实幻觉纠正收益"
            )
        else:
            bullets.append(
                f"Faithfulness：无检索 {naive['faithfulness']:.0%} → RAG {rag['faithfulness']:.0%} → RAG+自纠错 {checked['faithfulness']:.0%}"
            )
            bullets.append(
                f"幻觉率：无检索 {naive['hallucination_rate']:.0%} → RAG+自纠错 {checked['hallucination_rate']:.0%}，相对下降 {gen['hallucination_relative_drop']:.0%}"
            )
    e2e = report.get("e2e")
    if e2e:
        lat = e2e["latency_ms"]
        strategy_accuracy = e2e.get("strategy_accuracy")
        refusal_accuracy = e2e.get("refuse_accuracy")
        keyword_hit = e2e.get("keyword_hit")
        bullets.append(
            f"LabMate E2E {e2e['n']} 条：路由准确率 {_percent_text(strategy_accuracy)}；"
            f"拒答准确率 {_percent_text(refusal_accuracy)}；"
            f"关键词命中 {_percent_text(keyword_hit)}；"
            f"P50 {lat['p50']}ms / P95 {lat['p95']}ms"
        )
    return bullets


def _percent_text(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "n/a"


async def run_all(*, llm: bool) -> dict:
    print("Evaluating rules, overlay and retrieval ablations", file=sys.stderr, flush=True)
    report: dict = {
        "generated_at": datetime.now(UTC).isoformat(),
        "intent_rules": eval_intent_rules(),
        "intent_overlay": eval_intent_overlay(),
        "retrieval": await eval_retrieval(),
    }
    if llm:
        print("Evaluating intent without/with overlay", file=sys.stderr, flush=True)
        report["intent_v3_no_overlay"] = await eval_intent_llm(version="intent_v3", overlay=False)
        report["intent_v3"] = await eval_intent_llm(version="intent_v3", overlay=True)
        print("Evaluating generation cases", file=sys.stderr, flush=True)
        report["generation"] = await eval_generation()
        print("Evaluating end-to-end workflow", file=sys.stderr, flush=True)
        report["e2e"] = await eval_e2e()
    report["resume_bullets"] = _resume_bullets(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--task",
        choices=["all", "intent", "retrieval", "generation", "e2e"],
        default="all",
    )
    parser.add_argument("--llm", action="store_true")
    parser.add_argument(
        "--require-real-models",
        action="store_true",
        help="Stop on model fallback before paid evaluation",
    )
    args = parser.parse_args()

    async def _go() -> dict:
        if args.task == "all":
            return await run_all(llm=args.llm)
        if args.task == "intent":
            result: dict[str, Any] = {
                "intent_rules": eval_intent_rules(),
                "intent_overlay": eval_intent_overlay(),
            }
            if args.llm:
                result["intent_v3_no_overlay"] = await eval_intent_llm(
                    version="intent_v3", overlay=False
                )
                result["intent_v3"] = await eval_intent_llm(version="intent_v3", overlay=True)
            result["resume_bullets"] = _resume_bullets(result)
            return result
        if args.task == "retrieval":
            return {"retrieval": await eval_retrieval()}
        if args.task == "generation":
            return {"generation": await eval_generation()}
        return {"e2e": await eval_e2e()}

    async def _verified_go() -> dict:
        verification = await verify_real_models() if args.require_real_models else None
        if verification:
            print(f"Real models verified: {verification}", file=sys.stderr, flush=True)
        report = await _go()
        report["environment"] = evaluation_environment()
        if verification:
            report["model_verification"] = verification
        return report

    report = asyncio.run(_verified_go())
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = REPORT_DIR / f"{args.task}_{stamp}.json"
    latest = REPORT_DIR / "latest.json"
    text = json.dumps(report, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
