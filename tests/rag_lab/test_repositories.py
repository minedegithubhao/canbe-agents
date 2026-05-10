from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import DefaultClause

from app.repositories.mysql.base import Base
from app.repositories.mysql.dataset_repository import DatasetRepository
from app.repositories.mysql.eval_repository import EvalRepository
from app.repositories.mysql.models import (
    CaseResult,
    DatasetVersion,
    EvalCase,
    ExperimentRun,
    PipelineVersion,
)
from app.repositories.mysql.pipeline_repository import PipelineRepository
from app.repositories.mysql.run_repository import RunRepository


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = _create_sqlite_test_engine()
    metadata = _sqlite_metadata_from_models()
    metadata.create_all(engine)

    session_factory = sessionmaker(bind=engine, future=True)
    with session_factory() as session:
        yield session


def _create_sqlite_test_engine():
    engine = create_engine(
        "sqlite+pysqlite://",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def _sqlite_metadata_from_models():
    metadata = Base.metadata.__class__()
    for table in Base.metadata.sorted_tables:
        table_copy = table.to_metadata(metadata)
        for column in table_copy.columns:
            default = column.server_default
            if default is None:
                continue
            default_sql = str(default.arg).strip()
            if "UTC_TIMESTAMP()" in default_sql or "ON UPDATE" in default_sql:
                column.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
            elif "JSON_OBJECT()" in default_sql:
                column.server_default = DefaultClause(text("'{}'"))
    return metadata


def _pipeline_version_payload(version_no: int = 1) -> dict:
    return {
        "version_no": version_no,
        "chunking_config_json": {"strategy": "faq_atomic"},
        "retrieval_config_json": {"dense_enabled": True},
        "recall_config_json": {"fusion_strategy": "rrf"},
        "rerank_config_json": {"rerank_enabled": True},
        "prompt_config_json": {"system_prompt_template": "test"},
        "fallback_config_json": {"medium_confidence_threshold": 0.65},
        "status": "draft",
    }


def _assert_integrity_error_rolled_back(session: Session, operation) -> None:
    with pytest.raises(IntegrityError):
        operation()
    session.rollback()


def test_dataset_repository_alias_methods_forward_behavior(db_session: Session):
    repo = DatasetRepository(db_session)

    dataset = repo.create(
        code="faq",
        name="FAQ",
        knowledge_type="help",
        description="FAQ dataset",
    )
    listed = repo.list()
    loaded = repo.get(dataset.id)
    version = repo.create_version(
        dataset_id=dataset.id,
        version_no=1,
        source_type="jsonl",
        source_uri="exports/faq.jsonl",
        status="draft",
        document_count=10,
        chunk_count=20,
        metadata_json={"lang": "en-US"},
    )

    assert listed == [dataset]
    assert loaded is dataset
    assert version.dataset_id == dataset.id
    assert version.metadata_json == {"lang": "en-US"}


def test_dataset_repository_persists_dataset_and_version_with_real_session(db_session: Session):
    repo = DatasetRepository(db_session)

    first_dataset = repo.create_dataset(
        code="faq",
        name="FAQ",
        knowledge_type="help",
        description="FAQ dataset",
    )
    second_dataset = repo.create_dataset(
        code="guide",
        name="Guide",
        knowledge_type="manual",
        description="Guide dataset",
    )
    version = repo.create_dataset_version(
        dataset_id=first_dataset.id,
        version_no=1,
        source_type="jsonl",
        source_uri="exports/faq.jsonl",
        status="draft",
        document_count=10,
        chunk_count=20,
        metadata_json={"lang": "en-US"},
    )

    listed = repo.list_datasets()

    assert repo.get_dataset(first_dataset.id).code == "faq"
    assert [item.id for item in listed] == [first_dataset.id, second_dataset.id]
    assert version.dataset_id == first_dataset.id
    assert version.metadata_json == {"lang": "en-US"}
    assert db_session.get(DatasetVersion, version.id) is not None


def test_dataset_repository_returns_none_for_missing_dataset(db_session: Session):
    repo = DatasetRepository(db_session)

    assert repo.get_dataset(999) is None


def test_dataset_repository_rejects_duplicate_dataset_code(db_session: Session):
    repo = DatasetRepository(db_session)
    repo.create_dataset(code="faq", name="FAQ")

    _assert_integrity_error_rolled_back(
        db_session,
        lambda: repo.create_dataset(code="faq", name="FAQ duplicate"),
    )


def test_dataset_repository_rejects_duplicate_dataset_version_within_dataset(db_session: Session):
    repo = DatasetRepository(db_session)
    dataset = repo.create_dataset(code="faq", name="FAQ")
    repo.create_dataset_version(dataset_id=dataset.id, version_no=1)

    _assert_integrity_error_rolled_back(
        db_session,
        lambda: repo.create_dataset_version(dataset_id=dataset.id, version_no=1),
    )


def test_pipeline_repository_alias_methods_forward_behavior(db_session: Session):
    repo = PipelineRepository(db_session)

    pipeline = repo.create(code="baseline", name="Baseline", description="Default pipeline")
    version = repo.create_version(
        pipeline_id=pipeline.id,
        **_pipeline_version_payload(),
    )

    assert pipeline.code == "baseline"
    assert version.pipeline_id == pipeline.id
    assert version.chunking_config_json == {"strategy": "faq_atomic"}


def test_pipeline_repository_creates_versions_and_freezes_one(db_session: Session):
    repo = PipelineRepository(db_session)

    pipeline = repo.create_pipeline(code="baseline", name="Baseline", description="Default pipeline")
    version = repo.create_pipeline_version(
        pipeline_id=pipeline.id,
        **_pipeline_version_payload(),
    )
    frozen = repo.freeze_version(version.id)

    assert frozen.status == "frozen"
    assert db_session.get(PipelineVersion, version.id).status == "frozen"


def test_pipeline_repository_rejects_duplicate_code(db_session: Session):
    repo = PipelineRepository(db_session)
    repo.create_pipeline(code="baseline", name="Baseline")

    _assert_integrity_error_rolled_back(
        db_session,
        lambda: repo.create_pipeline(code="baseline", name="Baseline duplicate"),
    )


def test_pipeline_repository_rejects_duplicate_version_within_pipeline(db_session: Session):
    repo = PipelineRepository(db_session)
    pipeline = repo.create_pipeline(code="baseline", name="Baseline")
    repo.create_pipeline_version(
        pipeline_id=pipeline.id,
        **_pipeline_version_payload(version_no=1),
    )

    _assert_integrity_error_rolled_back(
        db_session,
        lambda: repo.create_pipeline_version(
            pipeline_id=pipeline.id,
            **_pipeline_version_payload(version_no=1),
        ),
    )


def test_pipeline_repository_freeze_version_raises_for_missing_id(db_session: Session):
    repo = PipelineRepository(db_session)

    with pytest.raises(ValueError, match=r"PipelineVersion not found: 999"):
        repo.freeze_version(999)


def test_eval_repository_alias_methods_forward_behavior(db_session: Session):
    dataset_repo = DatasetRepository(db_session)
    dataset = dataset_repo.create_dataset(code="faq", name="FAQ")
    repo = EvalRepository(db_session)

    eval_set = repo.create(
        code="faq-smoke",
        name="FAQ Smoke",
        dataset_id=dataset.id,
        description="Smoke coverage",
        generation_strategy="manual",
    )
    second_case = repo.add_case(eval_set_id=eval_set.id, query="Q2", case_no=2)
    first_case = repo.add_case(eval_set_id=eval_set.id, query="Q1", case_no=1)

    assert eval_set.dataset_id == dataset.id
    assert repo.list(eval_set.id) == [first_case, second_case]


def test_eval_repository_creates_eval_set_and_lists_cases_by_public_session_contract(db_session: Session):
    dataset_repo = DatasetRepository(db_session)
    dataset = dataset_repo.create_dataset(code="faq", name="FAQ")
    repo = EvalRepository(db_session)

    eval_set = repo.create_eval_set(
        code="faq-smoke",
        name="FAQ Smoke",
        dataset_id=dataset.id,
        description="Smoke coverage",
        generation_strategy="manual",
    )
    second_case = repo.add_case(
        eval_set_id=eval_set.id,
        query="How do I reset my password?",
        expected_answer="Use the password reset flow.",
        case_no=2,
        expected_sources_json={"urls": ["https://help.example.com/reset-password"]},
        labels_json={"topic": "account"},
        difficulty="easy",
        source_type="document",
        source_ref="doc-1",
        behavior_json={"should_answer": True},
        scoring_profile_json={"profile": "default"},
        enabled=True,
    )
    first_case = repo.add_case(
        eval_set_id=eval_set.id,
        query="How do I change my phone number?",
        expected_answer="Open account settings and update the phone number.",
        case_no=1,
        expected_sources_json={"urls": ["https://help.example.com/change-phone"]},
        labels_json={"topic": "account"},
        difficulty="easy",
        source_type="document",
        source_ref="doc-2",
        behavior_json={"should_answer": True},
        scoring_profile_json={"profile": "default"},
        enabled=True,
    )

    cases = repo.list_cases(eval_set.id)

    assert eval_set.dataset_id == dataset.id
    assert [item.id for item in cases] == [first_case.id, second_case.id]
    assert db_session.get(EvalCase, second_case.id).query == "How do I reset my password?"


def test_eval_repository_rejects_duplicate_eval_set_code(db_session: Session):
    repo = EvalRepository(db_session)
    repo.create_eval_set(code="faq-smoke", name="FAQ Smoke")

    _assert_integrity_error_rolled_back(
        db_session,
        lambda: repo.create_eval_set(code="faq-smoke", name="FAQ Smoke duplicate"),
    )


def test_eval_repository_rejects_duplicate_case_no_within_eval_set(db_session: Session):
    repo = EvalRepository(db_session)
    eval_set = repo.create_eval_set(code="faq-smoke", name="FAQ Smoke")
    repo.add_case(eval_set_id=eval_set.id, query="Question 1", case_no=1)

    _assert_integrity_error_rolled_back(
        db_session,
        lambda: repo.add_case(eval_set_id=eval_set.id, query="Question duplicate", case_no=1),
    )


def test_run_repository_alias_create_forwards_behavior(db_session: Session):
    dataset_repo = DatasetRepository(db_session)
    pipeline_repo = PipelineRepository(db_session)
    eval_repo = EvalRepository(db_session)
    run_repo = RunRepository(db_session)

    dataset = dataset_repo.create_dataset(code="faq", name="FAQ")
    dataset_version = dataset_repo.create_dataset_version(dataset_id=dataset.id, version_no=1)
    pipeline = pipeline_repo.create_pipeline(code="baseline", name="Baseline")
    pipeline_version = pipeline_repo.create_pipeline_version(
        pipeline_id=pipeline.id,
        **_pipeline_version_payload(),
    )
    eval_set = eval_repo.create_eval_set(code="faq-smoke", name="FAQ Smoke", dataset_id=dataset.id)

    run = run_repo.create(
        dataset_version_id=dataset_version.id,
        pipeline_version_id=pipeline_version.id,
        eval_set_id=eval_set.id,
        run_no=1,
        status="draft",
        triggered_by="tester",
    )

    assert run.status == "draft"
    assert run.triggered_by == "tester"


def test_run_repository_creates_run_updates_status_and_saves_results(db_session: Session):
    dataset_repo = DatasetRepository(db_session)
    pipeline_repo = PipelineRepository(db_session)
    eval_repo = EvalRepository(db_session)
    run_repo = RunRepository(db_session)

    dataset = dataset_repo.create_dataset(code="faq", name="FAQ")
    dataset_version = dataset_repo.create_dataset_version(dataset_id=dataset.id, version_no=1)
    pipeline = pipeline_repo.create_pipeline(code="baseline", name="Baseline")
    pipeline_version = pipeline_repo.create_pipeline_version(
        pipeline_id=pipeline.id,
        **_pipeline_version_payload(),
    )
    eval_set = eval_repo.create_eval_set(code="faq-smoke", name="FAQ Smoke", dataset_id=dataset.id)
    eval_case = eval_repo.add_case(eval_set_id=eval_set.id, query="Question", case_no=1)

    run = run_repo.create_run(
        dataset_version_id=dataset_version.id,
        pipeline_version_id=pipeline_version.id,
        eval_set_id=eval_set.id,
        run_no=1,
        status="draft",
        triggered_by="tester",
    )
    updated = run_repo.update_status(run.id, "running")
    result = run_repo.save_case_result(
        experiment_run_id=run.id,
        eval_case_id=eval_case.id,
        status="completed",
        fallback=False,
        answer="Answer",
        confidence=0.9,
        retrieval_score=0.8,
        rerank_score=0.7,
        judgement_json={"pass": True},
        trace_artifact_id=None,
    )
    summary = run_repo.save_summary(run.id, {"pass_rate": 1.0})

    assert updated.status == "running"
    assert result.judgement_json == {"pass": True}
    assert summary.summary_json == {"pass_rate": 1.0}
    assert db_session.get(ExperimentRun, run.id).summary_json == {"pass_rate": 1.0}
    assert db_session.get(CaseResult, result.id) is not None


def test_run_repository_save_case_result_raises_for_duplicate_run_case_pair(db_session: Session):
    dataset_repo = DatasetRepository(db_session)
    pipeline_repo = PipelineRepository(db_session)
    eval_repo = EvalRepository(db_session)
    run_repo = RunRepository(db_session)

    dataset = dataset_repo.create_dataset(code="faq", name="FAQ")
    dataset_version = dataset_repo.create_dataset_version(dataset_id=dataset.id, version_no=1)
    pipeline = pipeline_repo.create_pipeline(code="baseline", name="Baseline")
    pipeline_version = pipeline_repo.create_pipeline_version(
        pipeline_id=pipeline.id,
        **_pipeline_version_payload(),
    )
    eval_set = eval_repo.create_eval_set(code="faq-smoke", name="FAQ Smoke", dataset_id=dataset.id)
    eval_case = eval_repo.add_case(eval_set_id=eval_set.id, query="Question", case_no=1)
    run = run_repo.create_run(
        dataset_version_id=dataset_version.id,
        pipeline_version_id=pipeline_version.id,
        eval_set_id=eval_set.id,
        run_no=1,
    )

    run_repo.save_case_result(
        experiment_run_id=run.id,
        eval_case_id=eval_case.id,
        status="completed",
    )

    _assert_integrity_error_rolled_back(
        db_session,
        lambda: run_repo.save_case_result(
            experiment_run_id=run.id,
            eval_case_id=eval_case.id,
            status="completed",
        ),
    )


def test_run_repository_update_status_raises_for_missing_run(db_session: Session):
    repo = RunRepository(db_session)

    with pytest.raises(ValueError, match=r"ExperimentRun not found: 999"):
        repo.update_status(999, "running")


def test_run_repository_save_summary_raises_for_missing_run(db_session: Session):
    repo = RunRepository(db_session)

    with pytest.raises(ValueError, match=r"ExperimentRun not found: 999"):
        repo.save_summary(999, {"pass_rate": 0.0})


def test_sqlite_test_schema_enforces_foreign_keys_for_repository_tests(db_session: Session):
    repo = DatasetRepository(db_session)

    _assert_integrity_error_rolled_back(
        db_session,
        lambda: repo.create_dataset_version(dataset_id=999, version_no=1),
    )

    foreign_keys_enabled = db_session.execute(text("PRAGMA foreign_keys")).scalar_one()
    table_count = db_session.execute(
        text("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
    ).scalar_one()
    model_table_count = len(Base.metadata.tables)

    assert foreign_keys_enabled == 1
    assert table_count == model_table_count
