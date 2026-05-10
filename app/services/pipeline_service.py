from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.schemas.rag_lab.pipeline import (
    PipelineRunPreparation,
    PipelineRunPreparationStatus,
    PipelineVersionPayload,
)


class PipelineService:
    def __init__(self, pipeline_repository) -> None:
        self.pipeline_repository = pipeline_repository

    def list_pipelines(self) -> list[dict[str, Any]]:
        repository = self._require_repository()
        list_method = getattr(repository, "list_pipelines", None)
        if list_method is None:
            raise ValueError("pipeline_repository must implement list_pipelines()")
        return [self._serialize_pipeline(item) for item in list_method()]

    def create_pipeline(
        self,
        *,
        code: str,
        name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        repository = self._require_repository()
        create_method = getattr(repository, "create_pipeline", None) or getattr(repository, "create", None)
        if create_method is None:
            raise ValueError("pipeline_repository must implement create_pipeline()")
        pipeline = create_method(code=code, name=name, description=description)
        return self._serialize_pipeline(pipeline)

    def _normalize_payload(
        self, payload: PipelineVersionPayload | dict[str, Any]
    ) -> PipelineVersionPayload:
        if isinstance(payload, PipelineVersionPayload):
            return PipelineVersionPayload.model_validate(payload)
        return PipelineVersionPayload.model_validate(payload)

    def create_version(
        self,
        *,
        pipeline_id: int,
        version_no: int,
        payload: PipelineVersionPayload | dict[str, Any],
    ):
        validated_payload = self._normalize_payload(payload)
        return self.pipeline_repository.create_pipeline_version(
            pipeline_id=pipeline_id,
            version_no=version_no,
            chunking_config_json=validated_payload.chunking_config.model_dump(),
            retrieval_config_json=validated_payload.retrieval_config.model_dump(),
            recall_config_json=validated_payload.recall_config.model_dump(),
            rerank_config_json=validated_payload.rerank_config.model_dump(),
            prompt_config_json=validated_payload.prompt_config.model_dump(),
            fallback_config_json=validated_payload.fallback_config.model_dump(),
            status="draft",
        )

    def prepare_version_for_run(self, pipeline_version):
        """Ensure a runnable version is frozen exactly once."""
        try:
            run_preparation = PipelineRunPreparation.model_validate(
                {"status": pipeline_version.status}
            )
        except ValidationError as exc:
            raise ValueError(
                "Unsupported pipeline version status for run preparation: "
                f"{pipeline_version.status}"
            ) from exc
        if run_preparation.status is PipelineRunPreparationStatus.FROZEN:
            return pipeline_version
        if run_preparation.status is PipelineRunPreparationStatus.DRAFT:
            return self.pipeline_repository.freeze_version(pipeline_version.id)
        raise ValueError(
            f"Unsupported pipeline version status for run preparation: {pipeline_version.status}"
        )

    def _require_repository(self):
        if self.pipeline_repository is None:
            raise ValueError("pipeline_repository is required")
        return self.pipeline_repository

    def _serialize_pipeline(self, pipeline: Any) -> dict[str, Any]:
        if isinstance(pipeline, dict):
            return pipeline
        return {
            "id": getattr(pipeline, "id", None),
            "code": getattr(pipeline, "code", None),
            "name": getattr(pipeline, "name", None),
            "description": getattr(pipeline, "description", None),
        }
