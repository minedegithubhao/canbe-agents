from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EvalSetGenerateRequest(BaseModel):
    name: str = "jd_help_eval_v1"
    total_count: int = Field(default=100, ge=1, le=1000)
    category_distribution: dict[str, float] | None = None
    eval_type_distribution: dict[str, float] = Field(
        default_factory=lambda: {
            "single_faq_equivalent": 0.4,
            "colloquial_rewrite": 0.25,
            "typo_or_alias": 0.15,
            "near_miss_or_multi_faq": 0.1,
            "fallback_or_refusal": 0.1,
        }
    )
    difficulty_distribution: dict[str, float] = Field(default_factory=lambda: {"easy": 0.5, "medium": 0.35, "hard": 0.15})
    seed: int = 20260511
    source_path: str = "exports/jd_help_faq.cleaned.jsonl"

    @property
    def source_file(self) -> Path:
        return Path(self.source_path)


class EvalCase(BaseModel):
    case_id: str
    source_faq_ids: list[str] = Field(default_factory=list)
    category: str
    category_l1: str
    category_l2: str
    category_l3: str
    question: str
    question_style: str
    eval_type: str
    difficulty: str
    expected_route_category: str
    expected_retrieved_faq_ids: list[str] = Field(default_factory=list)
    reference_answer: str
    key_points: list[str] = Field(default_factory=list)
    forbidden_points: list[str] = Field(default_factory=list)
    must_refuse: bool = False
    source_url: str
    source_answer_hash: str
    generation_method: str = "clean_faq_rule_seeded"
    validation_status: str = "validated"
    notes: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GeneratedEvalSet(BaseModel):
    eval_set_id: str
    name: str
    source_path: str
    source_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    config: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, int] = Field(default_factory=dict)
    cases: list[EvalCase] = Field(default_factory=list)
