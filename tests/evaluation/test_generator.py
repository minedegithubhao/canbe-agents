from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.generator import EvalCaseGenerator, load_source_chunks, source_file_hash
from app.evaluation.schemas import EvalSetGenerateRequest


def test_load_source_chunks_maps_chunk_jsonl_fields(tmp_path: Path):
    chunks_path = tmp_path / "faq.chunks.jsonl"
    chunks_path.write_text(json.dumps(make_chunk_row("chunk_1", "FAQ_1"), ensure_ascii=False), encoding="utf-8")

    chunks = load_source_chunks(chunks_path)

    assert len(chunks) == 1
    assert chunks[0].chunk_id == "chunk_1"
    assert chunks[0].parent_faq_id == "FAQ_1"
    assert chunks[0].category == "订单相关"
    assert chunks[0].content == "订单未支付可取消重拍。"


def test_generator_creates_single_chunk_cases(tmp_path: Path):
    source_path = write_chunk_jsonl(tmp_path, [make_chunk_row("chunk_1", "FAQ_1")])
    request = EvalSetGenerateRequest(
        name="smoke",
        total_count=1,
        source_path=str(source_path),
        eval_type_distribution={"single_chunk": 1.0},
        question_style_distribution={"original": 1.0},
        difficulty_distribution={"easy": 1.0},
    )

    result = EvalCaseGenerator().generate(request)

    assert result.eval_set_id.startswith("eval_")
    assert result.source_hash == source_file_hash(source_path)
    assert result.summary == {"total": 1}
    case = result.cases[0]
    assert case.case_id == "faq_eval_000001"
    assert case.eval_type == "single_chunk"
    assert case.question_style == "original"
    assert case.difficulty == "easy"
    assert case.category == "订单相关"
    assert case.expected_retrieved_chunk_ids == ["chunk_1"]
    assert case.reference_contexts[0].chunk_id == "chunk_1"
    assert case.reference_contexts[0].parent_faq_id == "FAQ_1"


def test_generator_creates_multi_chunk_cases_from_same_category(tmp_path: Path):
    source_path = write_chunk_jsonl(
        tmp_path,
        [
            make_chunk_row("chunk_1", "FAQ_1", question="付款后改地址怎么办？"),
            make_chunk_row("chunk_2", "FAQ_2", question="付款后改规格怎么办？"),
            make_chunk_row("chunk_3", "FAQ_3", category="退款售后", question="退款多久到账？"),
        ],
    )
    request = EvalSetGenerateRequest(
        total_count=1,
        source_path=str(source_path),
        eval_type_distribution={"multi_chunk": 1.0},
        question_style_distribution={"colloquial": 1.0},
        difficulty_distribution={"hard": 1.0},
        category_distribution={"订单相关": 1.0},
    )

    result = EvalCaseGenerator().generate(request)

    case = result.cases[0]
    assert case.eval_type == "multi_chunk"
    assert case.question_style == "colloquial"
    assert case.difficulty == "hard"
    assert len(case.expected_retrieved_chunk_ids) == 2
    assert set(case.expected_retrieved_chunk_ids) == {"chunk_1", "chunk_2"}
    assert {context.chunk_id for context in case.reference_contexts} == {"chunk_1", "chunk_2"}


def test_generator_respects_category_distribution(tmp_path: Path):
    source_path = write_chunk_jsonl(
        tmp_path,
        [
            make_chunk_row("order_1", "FAQ_1", category="订单相关"),
            make_chunk_row("order_2", "FAQ_2", category="订单相关"),
            make_chunk_row("refund_1", "FAQ_3", category="退款售后"),
            make_chunk_row("refund_2", "FAQ_4", category="退款售后"),
        ],
    )
    request = EvalSetGenerateRequest(
        total_count=4,
        source_path=str(source_path),
        eval_type_distribution={"single_chunk": 1.0},
        question_style_distribution={"original": 1.0},
        difficulty_distribution={"easy": 1.0},
        category_distribution={"订单相关": 0.75, "退款售后": 0.25},
    )

    result = EvalCaseGenerator().generate(request)

    assert [case.category for case in result.cases].count("订单相关") == 3
    assert [case.category for case in result.cases].count("退款售后") == 1


def test_generator_defaults_to_chunk_data_category_distribution(tmp_path: Path):
    source_path = write_chunk_jsonl(
        tmp_path,
        [
            make_chunk_row("order_1", "FAQ_1", category="订单相关"),
            make_chunk_row("order_2", "FAQ_2", category="订单相关"),
            make_chunk_row("order_3", "FAQ_3", category="订单相关"),
            make_chunk_row("refund_1", "FAQ_4", category="退款售后"),
        ],
    )
    request = EvalSetGenerateRequest(
        total_count=4,
        source_path=str(source_path),
        eval_type_distribution={"single_chunk": 1.0},
        question_style_distribution={"original": 1.0},
        difficulty_distribution={"easy": 1.0},
    )

    result = EvalCaseGenerator().generate(request)

    assert [case.category for case in result.cases].count("订单相关") == 3
    assert [case.category for case in result.cases].count("退款售后") == 1


def write_chunk_jsonl(tmp_path: Path, rows: list[dict]) -> Path:
    source_path = tmp_path / "faq.chunks.jsonl"
    source_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    return source_path


def make_chunk_row(
    chunk_id: str,
    parent_id: str,
    *,
    category: str = "订单相关",
    question: str = "订单能修改规格吗？",
) -> dict:
    return {
        "id": chunk_id,
        "parent_id": parent_id,
        "url": f"https://help.jd.com/user/issue/{parent_id}.html",
        "category_l1": category,
        "category_l2": "订单修改",
        "category_l3": "规格修改",
        "question": question,
        "chunk_title": question,
        "chunk_text": "订单未支付可取消重拍。",
        "doc_type": "faq",
        "status": "active",
        "search_enabled": True,
    }
