from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.evaluation.schemas import EvalCase, EvalSetGenerateRequest, GeneratedEvalSet, ReferenceContext
from app.evaluation.text_repair import repair_text


EXCLUDED_DOC_TYPES = {"historical_rule", "compound_qa"}
ALLOWED_SOURCE_URL = "https://help.jd.com/user/issue.html"
ALLOWED_SOURCE_URL_PREFIX = "https://help.jd.com/user/issue/"


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    parent_faq_id: str
    question: str
    title: str
    content: str
    category: str
    category_l2: str
    category_l3: str
    source_url: str
    doc_type: str
    status: str
    search_enabled: bool


def source_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load_source_chunks(path: Path) -> list[SourceChunk]:
    chunks: list[SourceChunk] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            chunks.append(
                SourceChunk(
                    chunk_id=str(row.get("id") or row.get("chunk_id") or ""),
                    parent_faq_id=str(row.get("parent_id") or row.get("faq_id") or ""),
                    question=repair_text(str(row.get("question") or "")),
                    title=repair_text(str(row.get("chunk_title") or row.get("title") or row.get("question") or "")),
                    content=repair_text(str(row.get("chunk_text") or row.get("content") or row.get("answer_clean") or "")),
                    category=repair_text(str(row.get("category_l1") or row.get("category") or "未分类")),
                    category_l2=repair_text(str(row.get("category_l2") or "")),
                    category_l3=repair_text(str(row.get("category_l3") or "")),
                    source_url=str(row.get("url") or row.get("source_url") or ""),
                    doc_type=str(row.get("doc_type") or ""),
                    status=str(row.get("status") or ""),
                    search_enabled=bool(row.get("search_enabled", True)),
                )
            )
    return chunks


class EvalCaseGenerator:
    def generate(self, request: EvalSetGenerateRequest) -> GeneratedEvalSet:
        source_path = request.source_file
        chunks = self._eligible_chunks(load_source_chunks(source_path))
        if not chunks:
            raise ValueError("source_path does not contain eligible chunks")
        rng = random.Random()
        eval_types = expand_distribution(request.eval_type_distribution, request.total_count)
        question_styles = expand_distribution(request.question_style_distribution, request.total_count)
        difficulties = expand_distribution(request.difficulty_distribution, request.total_count)
        categories = expand_distribution(request.category_distribution or category_distribution_from_chunks(chunks), request.total_count)
        cases: list[EvalCase] = []
        for index in range(request.total_count):
            category = categories[index]
            pool = chunks_by_category(chunks, category) or chunks
            rng.shuffle(pool)
            eval_type = eval_types[index]
            selected = select_expected_chunks(pool, eval_type, rng)
            cases.append(
                self._case_from_chunks(
                    case_index=index + 1,
                    chunks=selected,
                    eval_type=eval_type,
                    question_style=question_styles[index],
                    difficulty=difficulties[index],
                )
            )
        return GeneratedEvalSet(
            eval_set_id=f"eval_{uuid4().hex}",
            name=request.name,
            source_path=str(source_path),
            source_hash=source_file_hash(source_path),
            config=request.model_dump(),
            summary={"total": len(cases)},
            cases=cases,
        )

    def _eligible_chunks(self, chunks: list[SourceChunk]) -> list[SourceChunk]:
        return [
            chunk
            for chunk in chunks
            if chunk.chunk_id
            and chunk.question
            and chunk.content
            and chunk.status == "active"
            and chunk.search_enabled
            and chunk.doc_type not in EXCLUDED_DOC_TYPES
            and is_allowed_source_url(chunk.source_url)
        ]

    def _case_from_chunks(
        self,
        *,
        case_index: int,
        chunks: list[SourceChunk],
        eval_type: str,
        question_style: str,
        difficulty: str,
    ) -> EvalCase:
        primary = chunks[0]
        question = transform_question(primary.question, question_style)
        return EvalCase(
            case_id=f"faq_eval_{case_index:06d}",
            question=question,
            eval_type=eval_type,
            question_style=question_style,
            difficulty=difficulty,
            category=primary.category,
            expected_retrieved_chunk_ids=[chunk.chunk_id for chunk in chunks],
            reference_contexts=[reference_context(chunk) for chunk in chunks],
        )


def reference_context(chunk: SourceChunk) -> ReferenceContext:
    return ReferenceContext(
        chunk_id=chunk.chunk_id,
        parent_faq_id=chunk.parent_faq_id,
        title=chunk.title,
        content=chunk.content,
        source_url=chunk.source_url,
    )


def category_distribution_from_chunks(chunks: list[SourceChunk]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk.category] = counts.get(chunk.category, 0) + 1
    total = sum(counts.values())
    return {category: count / total for category, count in counts.items()} if total else {}


def chunks_by_category(chunks: list[SourceChunk], category: str) -> list[SourceChunk]:
    return [chunk for chunk in chunks if chunk.category == category]


def select_expected_chunks(pool: list[SourceChunk], eval_type: str, rng: random.Random) -> list[SourceChunk]:
    if eval_type == "single_chunk" or len(pool) == 1:
        return [pool[0]]
    count = min(2, len(pool))
    return rng.sample(pool, count)


def expand_distribution(distribution: dict[str, float], total_count: int) -> list[str]:
    if total_count <= 0:
        return []
    items = [(key, max(float(value), 0.0)) for key, value in distribution.items() if value > 0]
    if not items:
        raise ValueError("distribution must contain at least one positive weight")
    total_weight = sum(value for _, value in items)
    raw_counts = [(key, value / total_weight * total_count) for key, value in items]
    counts = {key: int(raw) for key, raw in raw_counts}
    remaining = total_count - sum(counts.values())
    remainders = sorted(((raw - int(raw), key) for key, raw in raw_counts), reverse=True)
    for _, key in remainders[:remaining]:
        counts[key] += 1
    expanded: list[str] = []
    for key, _ in items:
        expanded.extend([key] * counts[key])
    return expanded[:total_count]


def transform_question(question: str, question_style: str) -> str:
    text = str(question or "").strip()
    if question_style == "colloquial":
        return text.rstrip("？?") + "怎么弄？"
    if question_style == "synonym":
        return text.replace("修改", "更改").replace("订单", "单子")
    if question_style == "abbreviated":
        return text.replace("怎么办", "").replace("吗？", "吗").strip()
    return text


def is_allowed_source_url(source_url: str) -> bool:
    return source_url == ALLOWED_SOURCE_URL or source_url.startswith(ALLOWED_SOURCE_URL_PREFIX)
