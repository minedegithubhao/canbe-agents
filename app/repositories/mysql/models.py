from sqlalchemy import CheckConstraint, JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.repositories.mysql.base import Base


UTC_NOW = text("(UTC_TIMESTAMP())")
UTC_NOW_ON_UPDATE = text("(UTC_TIMESTAMP()) ON UPDATE UTC_TIMESTAMP()")
JSON_EMPTY_OBJECT = text("(JSON_OBJECT())")


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    knowledge_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW_ON_UPDATE)


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint("dataset_id", "version_no"),
        CheckConstraint("version_no >= 0"),
        CheckConstraint("document_count >= 0"),
        CheckConstraint("chunk_count >= 0"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft", server_default=text("'draft'"))
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    doc_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW)


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint("chunk_no >= 0"),
        CheckConstraint("token_count >= 0"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"), nullable=False)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    chunk_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW)


class Pipeline(Base):
    __tablename__ = "pipelines"
    __table_args__ = (UniqueConstraint("code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW_ON_UPDATE)


class PipelineVersion(Base):
    __tablename__ = "pipeline_versions"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "version_no"),
        CheckConstraint("version_no >= 0"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_id: Mapped[int] = mapped_column(ForeignKey("pipelines.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    chunking_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    retrieval_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    recall_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    rerank_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    prompt_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    fallback_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft", server_default=text("'draft'"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW)


class EvalSet(Base):
    __tablename__ = "eval_sets"
    __table_args__ = (UniqueConstraint("code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_strategy: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW)


class EvalCase(Base):
    __tablename__ = "eval_cases"
    __table_args__ = (
        UniqueConstraint("eval_set_id", "case_no"),
        CheckConstraint("case_no >= 0"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eval_set_id: Mapped[int] = mapped_column(ForeignKey("eval_sets.id"), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    case_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    expected_sources_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    labels_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    difficulty: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    behavior_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    scoring_profile_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW)


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "pipeline_version_id", "eval_set_id", "run_no"),
        CheckConstraint("run_no >= 0"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"), nullable=False)
    pipeline_version_id: Mapped[int] = mapped_column(ForeignKey("pipeline_versions.id"), nullable=False)
    eval_set_id: Mapped[int] = mapped_column(ForeignKey("eval_sets.id"), nullable=False)
    run_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft", server_default=text("'draft'"))
    triggered_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    artifact_id: Mapped[int | None] = mapped_column(ForeignKey("artifacts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW)


class CaseResult(Base):
    __tablename__ = "case_results"
    __table_args__ = (UniqueConstraint("experiment_run_id", "eval_case_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_run_id: Mapped[int] = mapped_column(ForeignKey("experiment_runs.id"), nullable=False)
    eval_case_id: Mapped[int] = mapped_column(ForeignKey("eval_cases.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending", server_default=text("'pending'"))
    fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieval_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rerank_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    judgement_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    trace_artifact_id: Mapped[int | None] = mapped_column(ForeignKey("artifacts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW)


class RunComparison(Base):
    __tablename__ = "run_comparisons"
    __table_args__ = (UniqueConstraint("base_run_id", "target_run_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_run_id: Mapped[int] = mapped_column(ForeignKey("experiment_runs.id"), nullable=False)
    target_run_id: Mapped[int] = mapped_column(ForeignKey("experiment_runs.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending", server_default=text("'pending'"))
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    artifact_id: Mapped[int | None] = mapped_column(ForeignKey("artifacts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_type: Mapped[str] = mapped_column(String(64), nullable=False, default="local", server_default=text("'local'"))
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=JSON_EMPTY_OBJECT)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=UTC_NOW)
