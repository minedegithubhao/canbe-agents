from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import sessionmaker

from app.repositories.mysql.base import Base
from app.repositories.mysql.models import (
    Artifact,
    CaseResult,
    Chunk,
    Dataset,
    DatasetVersion,
    Document,
    EvalCase,
    EvalSet,
    ExperimentRun,
    Pipeline,
    PipelineVersion,
    RunComparison,
)
from app.repositories.mysql.session import get_engine, get_session_factory


def test_core_models_define_expected_tables_and_spec_columns():
    expected_tables = {
        "artifacts",
        "case_results",
        "chunks",
        "dataset_versions",
        "datasets",
        "documents",
        "eval_cases",
        "eval_sets",
        "experiment_runs",
        "pipeline_versions",
        "pipelines",
        "run_comparisons",
    }

    assert Dataset.__tablename__ == "datasets"
    assert DatasetVersion.__tablename__ == "dataset_versions"
    assert Pipeline.__tablename__ == "pipelines"
    assert PipelineVersion.__tablename__ == "pipeline_versions"
    assert expected_tables.issubset(Base.metadata.tables.keys())

    assert {"code", "knowledge_type", "description", "created_at", "updated_at"}.issubset(Dataset.__table__.columns.keys())
    assert {
        "version_no",
        "source_type",
        "source_uri",
        "status",
        "document_count",
        "chunk_count",
        "metadata_json",
        "created_at",
    }.issubset(DatasetVersion.__table__.columns.keys())
    assert {"title", "doc_type", "source_url", "content_hash", "metadata_json"}.issubset(Document.__table__.columns.keys())
    assert {"chunk_no", "content_hash", "token_count", "metadata_json"}.issubset(Chunk.__table__.columns.keys())
    assert {"code", "description", "created_at", "updated_at"}.issubset(Pipeline.__table__.columns.keys())
    assert {
        "version_no",
        "chunking_config_json",
        "retrieval_config_json",
        "recall_config_json",
        "rerank_config_json",
        "prompt_config_json",
        "fallback_config_json",
        "status",
        "created_at",
    }.issubset(PipelineVersion.__table__.columns.keys())
    assert {"name", "code", "dataset_id", "description", "generation_strategy", "created_at"}.issubset(
        EvalSet.__table__.columns.keys()
    )
    assert {
        "case_no",
        "expected_sources_json",
        "labels_json",
        "difficulty",
        "source_type",
        "source_ref",
        "behavior_json",
        "scoring_profile_json",
        "enabled",
        "created_at",
    }.issubset(EvalCase.__table__.columns.keys())
    assert {"run_no", "status", "triggered_by", "started_at", "finished_at", "summary_json", "artifact_id"}.issubset(
        ExperimentRun.__table__.columns.keys()
    )
    assert {
        "status",
        "fallback",
        "answer",
        "confidence",
        "retrieval_score",
        "rerank_score",
        "judgement_json",
        "trace_artifact_id",
        "created_at",
    }.issubset(CaseResult.__table__.columns.keys())
    assert "trace_snapshot" not in CaseResult.__table__.columns.keys()
    assert {"base_run_id", "target_run_id", "status", "summary_json", "artifact_id", "created_at"}.issubset(
        RunComparison.__table__.columns.keys()
    )
    assert {"artifact_type", "storage_type", "storage_path", "content_hash", "metadata_json", "created_at"}.issubset(
        Artifact.__table__.columns.keys()
    )
    assert Dataset.__table__.c.created_at.type.timezone is False
    assert Dataset.__table__.c.updated_at.type.timezone is False
    assert ExperimentRun.__table__.c.started_at.type.timezone is False
    assert ExperimentRun.__table__.c.finished_at.type.timezone is False


def test_each_required_model_exposes_expected_tablename():
    expected_tablenames = {
        Dataset: "datasets",
        DatasetVersion: "dataset_versions",
        Document: "documents",
        Chunk: "chunks",
        Pipeline: "pipelines",
        PipelineVersion: "pipeline_versions",
        EvalSet: "eval_sets",
        EvalCase: "eval_cases",
        ExperimentRun: "experiment_runs",
        CaseResult: "case_results",
        RunComparison: "run_comparisons",
        Artifact: "artifacts",
    }

    for model, expected_tablename in expected_tablenames.items():
        assert model.__tablename__ == expected_tablename


def test_required_unique_constraints_exist():
    dataset_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in Dataset.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    dataset_version_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in DatasetVersion.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    pipeline_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in Pipeline.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    pipeline_version_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in PipelineVersion.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    eval_set_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in EvalSet.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    eval_case_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in EvalCase.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    experiment_run_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in ExperimentRun.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    case_result_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in CaseResult.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    run_comparison_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in RunComparison.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("code",) in dataset_constraints
    assert ("dataset_id", "version_no") in dataset_version_constraints
    assert ("code",) in pipeline_constraints
    assert ("pipeline_id", "version_no") in pipeline_version_constraints
    assert ("code",) in eval_set_constraints
    assert ("eval_set_id", "case_no") in eval_case_constraints
    assert ("dataset_version_id", "pipeline_version_id", "eval_set_id", "run_no") in experiment_run_constraints
    assert ("experiment_run_id", "eval_case_id") in case_result_constraints
    assert ("base_run_id", "target_run_id") in run_comparison_constraints


def test_required_non_negative_check_constraints_exist():
    dataset_version_checks = {constraint.sqltext.text for constraint in DatasetVersion.__table__.constraints if isinstance(constraint, CheckConstraint)}
    chunk_checks = {constraint.sqltext.text for constraint in Chunk.__table__.constraints if isinstance(constraint, CheckConstraint)}
    pipeline_version_checks = {
        constraint.sqltext.text for constraint in PipelineVersion.__table__.constraints if isinstance(constraint, CheckConstraint)
    }
    eval_case_checks = {constraint.sqltext.text for constraint in EvalCase.__table__.constraints if isinstance(constraint, CheckConstraint)}
    experiment_run_checks = {
        constraint.sqltext.text for constraint in ExperimentRun.__table__.constraints if isinstance(constraint, CheckConstraint)
    }

    assert "version_no >= 0" in dataset_version_checks
    assert "document_count >= 0" in dataset_version_checks
    assert "chunk_count >= 0" in dataset_version_checks
    assert "chunk_no >= 0" in chunk_checks
    assert "token_count >= 0" in chunk_checks
    assert "version_no >= 0" in pipeline_version_checks
    assert "case_no >= 0" in eval_case_checks
    assert "run_no >= 0" in experiment_run_checks


def test_core_fields_expose_mysql_safe_server_defaults():
    assert str(Dataset.__table__.c.created_at.server_default.arg) == "(UTC_TIMESTAMP())"
    assert str(Dataset.__table__.c.updated_at.server_default.arg) == "(UTC_TIMESTAMP()) ON UPDATE UTC_TIMESTAMP()"

    assert str(DatasetVersion.__table__.c.version_no.server_default.arg) == "1"
    assert str(DatasetVersion.__table__.c.status.server_default.arg) == "'draft'"
    assert str(DatasetVersion.__table__.c.document_count.server_default.arg) == "0"
    assert str(DatasetVersion.__table__.c.chunk_count.server_default.arg) == "0"
    assert str(DatasetVersion.__table__.c.metadata_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(DatasetVersion.__table__.c.created_at.server_default.arg) == "(UTC_TIMESTAMP())"

    assert str(Chunk.__table__.c.chunk_no.server_default.arg) == "0"
    assert str(Chunk.__table__.c.token_count.server_default.arg) == "0"
    assert str(Chunk.__table__.c.metadata_json.server_default.arg) == "(JSON_OBJECT())"

    assert str(PipelineVersion.__table__.c.version_no.server_default.arg) == "1"
    assert str(PipelineVersion.__table__.c.chunking_config_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(PipelineVersion.__table__.c.retrieval_config_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(PipelineVersion.__table__.c.recall_config_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(PipelineVersion.__table__.c.rerank_config_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(PipelineVersion.__table__.c.prompt_config_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(PipelineVersion.__table__.c.fallback_config_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(PipelineVersion.__table__.c.status.server_default.arg) == "'draft'"
    assert str(PipelineVersion.__table__.c.created_at.server_default.arg) == "(UTC_TIMESTAMP())"

    assert str(EvalCase.__table__.c.case_no.server_default.arg) == "1"
    assert str(EvalCase.__table__.c.expected_sources_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(EvalCase.__table__.c.labels_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(EvalCase.__table__.c.behavior_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(EvalCase.__table__.c.scoring_profile_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(EvalCase.__table__.c.enabled.server_default.arg) == "1"
    assert str(EvalCase.__table__.c.created_at.server_default.arg) == "(UTC_TIMESTAMP())"

    assert str(ExperimentRun.__table__.c.run_no.server_default.arg) == "1"
    assert str(ExperimentRun.__table__.c.status.server_default.arg) == "'draft'"
    assert str(ExperimentRun.__table__.c.summary_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(ExperimentRun.__table__.c.created_at.server_default.arg) == "(UTC_TIMESTAMP())"

    assert str(CaseResult.__table__.c.status.server_default.arg) == "'pending'"
    assert str(CaseResult.__table__.c.fallback.server_default.arg) == "0"
    assert str(CaseResult.__table__.c.judgement_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(CaseResult.__table__.c.created_at.server_default.arg) == "(UTC_TIMESTAMP())"

    assert str(RunComparison.__table__.c.status.server_default.arg) == "'pending'"
    assert str(RunComparison.__table__.c.summary_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(RunComparison.__table__.c.created_at.server_default.arg) == "(UTC_TIMESTAMP())"

    assert str(Artifact.__table__.c.storage_type.server_default.arg) == "'local'"
    assert str(Artifact.__table__.c.metadata_json.server_default.arg) == "(JSON_OBJECT())"
    assert str(Artifact.__table__.c.created_at.server_default.arg) == "(UTC_TIMESTAMP())"


def test_session_setup_reuses_cached_engine_and_factory():
    engine = get_engine()
    repeated_engine = get_engine()
    factory = get_session_factory()
    repeated_factory = get_session_factory()

    assert engine is repeated_engine
    assert isinstance(factory, sessionmaker)
    assert factory is repeated_factory
    assert factory.kw["bind"] is not None
    assert factory.kw["bind"] is engine
