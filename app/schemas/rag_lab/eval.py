from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvalCaseLabelSet(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    topic: str = Field(default="general")
    difficulty: str = Field(default="medium")
    source_type: str = Field(default="cleaned_document")


class EvalCaseBehavior(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    should_answer: bool = Field(default=True)
    should_cite_sources: bool = Field(default=True)
    should_refuse: bool = Field(default=False)


class EvalCaseScoringProfile(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    profile: str = Field(default="default")
    answer_correctness_weight: float = Field(default=0.4)
    faithfulness_weight: float = Field(default=0.3)
    source_grounding_weight: float = Field(default=0.2)
    fallback_behavior_weight: float = Field(default=0.1)


class EvalCasePayload(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    external_id: str = Field(...)
    query: str = Field(...)
    expected_answer: str = Field(...)
    source_url: str | None = Field(default=None)
    labels: EvalCaseLabelSet = Field(default_factory=EvalCaseLabelSet)
    behavior: EvalCaseBehavior = Field(default_factory=EvalCaseBehavior)
    scoring_profile: EvalCaseScoringProfile = Field(
        default_factory=EvalCaseScoringProfile
    )


class EvalDocumentInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    id: str | int = Field(...)
    question: str = Field(...)
    answer: str = Field(...)
    sourceUrl: str | None = Field(default=None)
    category: str | None = Field(default=None)
    topic: str | None = Field(default=None)


class EvalSetRecord(BaseModel):
    model_config = ConfigDict(
        extra="ignore", validate_assignment=True, revalidate_instances="always"
    )

    id: int | None = Field(default=None)
    code: str | None = Field(default=None)
    name: str | None = Field(default=None)
    dataset_id: int | None = Field(default=None)
    description: str | None = Field(default=None)
    generation_strategy: str | None = Field(default=None)


class EvalCaseRecord(BaseModel):
    model_config = ConfigDict(
        extra="ignore", validate_assignment=True, revalidate_instances="always"
    )

    id: int | None = Field(default=None)
    eval_set_id: int | None = Field(default=None)
    case_payload: EvalCasePayload = Field(...)
