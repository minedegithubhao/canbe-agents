from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.rag_lab.pipeline import (
    ChunkingConfig,
    FallbackConfig,
    PipelineRunPreparation,
    PipelineRunPreparationStatus,
    PipelineVersionPayload,
    PromptConfig,
    RecallConfig,
    RerankConfig,
    RetrievalConfig,
)
from app.services.pipeline_service import PipelineService


def test_pipeline_payload_requires_named_config_blocks():
    payload = PipelineVersionPayload(
        chunking_config={"strategy": "faq_atomic"},
        retrieval_config={"dense_enabled": True},
        recall_config={"fusion_strategy": "rrf"},
        rerank_config={"rerank_enabled": True},
        prompt_config={"system_prompt_template": "test"},
        fallback_config={"medium_confidence_threshold": 0.65},
    )

    assert isinstance(payload.chunking_config, ChunkingConfig)
    assert isinstance(payload.retrieval_config, RetrievalConfig)
    assert isinstance(payload.recall_config, RecallConfig)
    assert isinstance(payload.rerank_config, RerankConfig)
    assert isinstance(payload.prompt_config, PromptConfig)
    assert isinstance(payload.fallback_config, FallbackConfig)
    assert payload.chunking_config.strategy == "faq_atomic"


def test_pipeline_payload_rejects_missing_named_config_block():
    with pytest.raises(ValidationError, match="retrieval_config"):
        PipelineVersionPayload(
            chunking_config={"strategy": "faq_atomic"},
            recall_config={"fusion_strategy": "rrf"},
            rerank_config={"rerank_enabled": True},
            prompt_config={"system_prompt_template": "test"},
            fallback_config={"medium_confidence_threshold": 0.65},
        )


def test_pipeline_run_preparation_schema_allows_only_freezeable_statuses():
    draft = PipelineRunPreparation(status="draft")
    frozen = PipelineRunPreparation(status="frozen")

    assert draft.status is PipelineRunPreparationStatus.DRAFT
    assert frozen.status is PipelineRunPreparationStatus.FROZEN

    with pytest.raises(ValidationError, match="status"):
        PipelineRunPreparation(status="archived")


def test_pipeline_service_validates_payload_at_boundary():
    repo = _FakePipelineRepository()
    service = PipelineService(repo)

    with pytest.raises(ValidationError, match="retrieval_config"):
        service.create_version(
            pipeline_id=7,
            version_no=3,
            payload={
                "chunking_config": {"strategy": "faq_atomic"},
                "recall_config": {"fusion_strategy": "rrf"},
                "rerank_config": {"rerank_enabled": True},
                "prompt_config": {"system_prompt_template": "test"},
                "fallback_config": {"medium_confidence_threshold": 0.65},
            },
        )


def test_pipeline_service_revalidates_prebuilt_payload_instance_before_persisting():
    repo = _FakePipelineRepository()
    service = PipelineService(repo)
    payload = PipelineVersionPayload.model_construct(
        chunking_config=ChunkingConfig(strategy="faq_atomic"),
        retrieval_config=RetrievalConfig.model_construct(),
        recall_config=RecallConfig(fusion_strategy="rrf"),
        rerank_config=RerankConfig(rerank_enabled=True),
        prompt_config=PromptConfig(system_prompt_template="test"),
        fallback_config=FallbackConfig(medium_confidence_threshold=0.65),
    )

    with pytest.raises(ValidationError, match="retrieval_config"):
        service.create_version(
            pipeline_id=7,
            version_no=3,
            payload=payload,
        )


def test_pipeline_service_creates_version_with_all_named_blocks():
    repo = _FakePipelineRepository()
    service = PipelineService(repo)

    version = service.create_version(
        pipeline_id=7,
        version_no=3,
        payload={
            "chunking_config": {"strategy": "faq_atomic"},
            "retrieval_config": {"dense_enabled": True},
            "recall_config": {"fusion_strategy": "rrf"},
            "rerank_config": {"rerank_enabled": True},
            "prompt_config": {"system_prompt_template": "test"},
            "fallback_config": {"medium_confidence_threshold": 0.65},
        },
    )

    assert version.pipeline_id == 7
    assert version.version_no == 3
    assert version.retrieval_config_json == {"dense_enabled": True}
    assert version.status == "draft"


def test_pipeline_service_prepare_version_for_run_freezes_draft_version():
    repo = _FakePipelineRepository()
    service = PipelineService(repo)

    frozen = service.prepare_version_for_run(
        _FakePipelineVersion(
            pipeline_id=7,
            version_no=3,
            status="draft",
        )
    )

    assert frozen.status == "frozen"
    assert repo.frozen_ids == [frozen.id]


def test_pipeline_service_prepare_version_for_run_leaves_frozen_version_unchanged():
    repo = _FakePipelineRepository()
    service = PipelineService(repo)
    existing = _FakePipelineVersion(
        pipeline_id=7,
        version_no=3,
        status="frozen",
        version_id=9,
    )

    result = service.prepare_version_for_run(existing)

    assert result is existing
    assert repo.frozen_ids == []


def test_pipeline_service_prepare_version_for_run_rejects_unsupported_status():
    repo = _FakePipelineRepository()
    service = PipelineService(repo)
    archived = _FakePipelineVersion(
        pipeline_id=7,
        version_no=3,
        status="archived",
        version_id=9,
    )

    with pytest.raises(ValueError, match="archived"):
        service.prepare_version_for_run(archived)

    assert repo.frozen_ids == []


def test_pipeline_service_has_one_public_run_preparation_method():
    assert hasattr(PipelineService, "prepare_version_for_run")
    assert not hasattr(PipelineService, "freeze_version_for_run")


class _FakePipelineVersion:
    def __init__(
        self,
        *,
        pipeline_id: int,
        version_no: int,
        status: str,
        version_id: int = 1,
        chunking_config_json: dict | None = None,
        retrieval_config_json: dict | None = None,
        recall_config_json: dict | None = None,
        rerank_config_json: dict | None = None,
        prompt_config_json: dict | None = None,
        fallback_config_json: dict | None = None,
    ) -> None:
        self.id = version_id
        self.pipeline_id = pipeline_id
        self.version_no = version_no
        self.status = status
        self.chunking_config_json = chunking_config_json or {}
        self.retrieval_config_json = retrieval_config_json or {}
        self.recall_config_json = recall_config_json or {}
        self.rerank_config_json = rerank_config_json or {}
        self.prompt_config_json = prompt_config_json or {}
        self.fallback_config_json = fallback_config_json or {}


class _FakePipelineRepository:
    def __init__(self) -> None:
        self.created_payloads: list[dict] = []
        self.frozen_ids: list[int] = []

    def create_pipeline_version(self, **kwargs):
        self.created_payloads.append(kwargs)
        return _FakePipelineVersion(
            pipeline_id=kwargs["pipeline_id"],
            version_no=kwargs["version_no"],
            status=kwargs["status"],
            chunking_config_json=kwargs["chunking_config_json"],
            retrieval_config_json=kwargs["retrieval_config_json"],
            recall_config_json=kwargs["recall_config_json"],
            rerank_config_json=kwargs["rerank_config_json"],
            prompt_config_json=kwargs["prompt_config_json"],
            fallback_config_json=kwargs["fallback_config_json"],
        )

    def freeze_version(self, pipeline_version_id: int):
        self.frozen_ids.append(pipeline_version_id)
        return _FakePipelineVersion(
            pipeline_id=7,
            version_no=3,
            status="frozen",
            version_id=pipeline_version_id,
        )
