from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ChunkingConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    strategy: str = Field(...)


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    dense_enabled: bool = Field(...)


class RecallConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    fusion_strategy: str = Field(...)


class RerankConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    rerank_enabled: bool = Field(...)


class PromptConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    system_prompt_template: str = Field(...)


class FallbackConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    medium_confidence_threshold: float = Field(...)


class PipelineRunPreparationStatus(str, Enum):
    DRAFT = "draft"
    FROZEN = "frozen"


class PipelineRunPreparation(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    status: PipelineRunPreparationStatus = Field(...)


class PipelineVersionPayload(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    chunking_config: ChunkingConfig = Field(...)
    retrieval_config: RetrievalConfig = Field(...)
    recall_config: RecallConfig = Field(...)
    rerank_config: RerankConfig = Field(...)
    prompt_config: PromptConfig = Field(...)
    fallback_config: FallbackConfig = Field(...)
