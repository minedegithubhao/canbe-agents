from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class DatasetSourceSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    cleaned_path: str = Field(...)
    chunk_path: str | None = Field(default=None)
    document_count: int = Field(...)
    chunk_count: int = Field(...)


class DatasetVersionMetadata(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_assignment=True, revalidate_instances="always"
    )

    source_type: str = Field(default="jsonl")
    cleaned_path: str = Field(...)
    chunk_path: str | None = Field(default=None)
    document_count: int = Field(...)
    chunk_count: int = Field(...)

    @classmethod
    def from_summary(
        cls,
        cleaned_path: Path,
        chunk_path: Path | None,
        summary: DatasetSourceSummary,
    ) -> "DatasetVersionMetadata":
        return cls(
            cleaned_path=str(cleaned_path),
            chunk_path=None if chunk_path is None else str(chunk_path),
            document_count=summary.document_count,
            chunk_count=summary.chunk_count,
        )
