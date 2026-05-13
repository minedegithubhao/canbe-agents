from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


ALLOWED_EVAL_TYPES = {"single_chunk", "multi_chunk"}
ALLOWED_QUESTION_STYLES = {"original", "colloquial", "synonym", "abbreviated"}
ALLOWED_DIFFICULTIES = {"easy", "medium", "hard"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_distribution(
    value: dict[str, float],
    *,
    allowed_keys: set[str] | None,
    label: str,
) -> dict[str, float]:
    if not value:
        raise ValueError(f"{label} must contain at least one item")
    unsupported = sorted(set(value) - allowed_keys) if allowed_keys is not None else []
    if unsupported:
        raise ValueError(f"unsupported {label}: {', '.join(unsupported)}")
    normalized = {key: float(weight) for key, weight in value.items()}
    if any(weight < 0 for weight in normalized.values()):
        raise ValueError(f"{label} cannot contain negative weights")
    total = sum(normalized.values())
    if abs(total - 1.0) > 0.000001:
        raise ValueError(f"{label} must sum to 1.0")
    return normalized


class EvalSetGenerateRequest(BaseModel):
    name: str = "jd_help_eval_v1"
    total_count: int = Field(default=100, ge=1, le=1000)
    seed: int = 20260513
    source_path: str = "exports/jd_help_faq.cleaned.jsonl"
    eval_type_distribution: dict[str, float] = Field(default_factory=lambda: {"single_chunk": 0.7, "multi_chunk": 0.3})
    question_style_distribution: dict[str, float] = Field(
        default_factory=lambda: {
            "original": 0.3,
            "colloquial": 0.4,
            "synonym": 0.2,
            "abbreviated": 0.1,
        }
    )
    difficulty_distribution: dict[str, float] = Field(default_factory=lambda: {"easy": 0.3, "medium": 0.5, "hard": 0.2})
    category_distribution: dict[str, float] | None = None

    @field_validator("eval_type_distribution")
    @classmethod
    def validate_eval_type_distribution(cls, value: dict[str, float]) -> dict[str, float]:
        return validate_distribution(value, allowed_keys=ALLOWED_EVAL_TYPES, label="eval_type")

    @field_validator("question_style_distribution")
    @classmethod
    def validate_question_style_distribution(cls, value: dict[str, float]) -> dict[str, float]:
        return validate_distribution(value, allowed_keys=ALLOWED_QUESTION_STYLES, label="question_style")

    @field_validator("difficulty_distribution")
    @classmethod
    def validate_difficulty_distribution(cls, value: dict[str, float]) -> dict[str, float]:
        return validate_distribution(value, allowed_keys=ALLOWED_DIFFICULTIES, label="difficulty")

    @field_validator("category_distribution")
    @classmethod
    def validate_category_distribution(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is None:
            return None
        return validate_distribution(value, allowed_keys=None, label="category")

    @property
    def source_file(self) -> Path:
        return Path(self.source_path)


class ReferenceContext(BaseModel):
    chunk_id: str
    parent_faq_id: str = ""
    title: str = ""
    content: str = ""
    source_url: str = ""


class EvalCase(BaseModel):
    case_id: str
    eval_set_id: str = ""
    question: str
    eval_type: str
    question_style: str
    difficulty: str
    category: str
    expected_retrieved_chunk_ids: list[str] = Field(default_factory=list)
    reference_contexts: list[ReferenceContext] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_case(self) -> EvalCase:
        if self.eval_type not in ALLOWED_EVAL_TYPES:
            raise ValueError(f"unsupported eval_type: {self.eval_type}")
        if self.question_style not in ALLOWED_QUESTION_STYLES:
            raise ValueError(f"unsupported question_style: {self.question_style}")
        if self.difficulty not in ALLOWED_DIFFICULTIES:
            raise ValueError(f"unsupported difficulty: {self.difficulty}")
        if not self.expected_retrieved_chunk_ids:
            raise ValueError("expected_retrieved_chunk_ids must not be empty")
        return self


class GeneratedEvalSet(BaseModel):
    eval_set_id: str
    name: str
    source_path: str
    source_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str = "admin"
    config: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, int] = Field(default_factory=dict)
    cases: list[EvalCase] = Field(default_factory=list)


class EvalRunConfig(BaseModel):
    configured_k: int = Field(default=5, ge=1, le=50)
    retrieval_top_n: int = Field(default=20, ge=1, le=200)
    similarity_threshold: float = Field(default=0.72, ge=0.0, le=1.0)
    rerank_enabled: bool = True
    case_concurrency_override: int | None = Field(default=None, ge=1, le=50)
    commit_batch_size_override: int | None = Field(default=None, ge=1, le=200)


class EvalRunSummary(BaseModel):
    total: int = 0
    hit_at_k: float = 0.0
    context_recall_at_k: float = 0.0
    mrr_at_k: float = 0.0
    precision_at_configured_k: float = 0.0
    precision_at_effective_k: float = 0.0
    avg_effective_k: float = 0.0
    zero_context_rate: float = 0.0


class EvalCaseMetrics(BaseModel):
    hit_at_k: int
    context_recall_at_k: float
    mrr_at_k: float
    precision_at_configured_k: float
    precision_at_effective_k: float
    effective_k: int
    matched_chunk_ids: list[str] = Field(default_factory=list)


class RetrievedContext(BaseModel):
    chunk_id: str
    parent_faq_id: str = ""
    score: float = 0.0
    matched: bool = False
    content: str = ""
    source_url: str = ""


class EvalRunDiagnostics(BaseModel):
    configured_k: int
    effective_k: int
    similarity_threshold: float
    expected_chunk_ids: list[str] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    matched_chunk_ids: list[str] = Field(default_factory=list)
    retrieved_contexts: list[RetrievedContext] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)


class EvalRunResult(BaseModel):
    run_id: str
    eval_set_id: str
    case_id: str
    question: str
    eval_type: str
    question_style: str
    difficulty: str
    category: str
    metrics: EvalCaseMetrics
    diagnostics: EvalRunDiagnostics
    created_at: datetime = Field(default_factory=utc_now)
