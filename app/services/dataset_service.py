from __future__ import annotations

from pathlib import Path
from typing import Any

from app.schemas.rag_lab.dataset import DatasetSourceSummary, DatasetVersionMetadata
from app.services.ingest_service import IngestService


class DatasetService:
    def __init__(
        self,
        dataset_repository: Any,
        dataset_version_repository: Any,
        ingest_service: IngestService | None,
    ) -> None:
        self.dataset_repository = dataset_repository
        self.dataset_version_repository = dataset_version_repository
        self.ingest_service = ingest_service

    def inspect_sources(
        self,
        cleaned_path: Path | str,
        chunk_path: Path | str | None,
    ) -> dict[str, Any]:
        cleaned = Path(cleaned_path)
        chunk = None if chunk_path is None else Path(chunk_path)

        faq_rows, chunk_rows = IngestService.load_source_rows(cleaned, chunk)
        summary = DatasetSourceSummary(
            cleaned_path=str(cleaned),
            chunk_path=None if chunk is None else str(chunk),
            document_count=len(faq_rows),
            chunk_count=len(chunk_rows),
        )
        return summary.model_dump()

    def list_datasets(self) -> list[dict[str, Any]]:
        repository = self.dataset_repository
        if repository is None:
            raise ValueError("dataset_repository is required to list datasets")
        list_method = getattr(repository, "list_datasets", None) or getattr(repository, "list", None)
        if list_method is None:
            raise ValueError("dataset_repository must implement list_datasets()")
        return [self._serialize_dataset(item) for item in list_method()]

    def create_dataset(
        self,
        *,
        code: str,
        name: str,
        knowledge_type: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        repository = self.dataset_repository
        if repository is None:
            raise ValueError("dataset_repository is required to create datasets")
        create_method = getattr(repository, "create_dataset", None) or getattr(repository, "create", None)
        if create_method is None:
            raise ValueError("dataset_repository must implement create_dataset()")
        dataset = create_method(
            code=code,
            name=name,
            knowledge_type=knowledge_type,
            description=description,
        )
        return self._serialize_dataset(dataset)

    def build_version_metadata(
        self,
        cleaned_path: Path | str,
        chunk_path: Path | str | None,
    ) -> dict[str, Any]:
        cleaned = Path(cleaned_path)
        chunk = None if chunk_path is None else Path(chunk_path)
        summary = DatasetSourceSummary.model_validate(
            self.inspect_sources(cleaned, chunk)
        )
        return DatasetVersionMetadata.from_summary(cleaned, chunk, summary).model_dump()

    async def ingest_version(
        self,
        cleaned_path: Path | str,
        chunk_path: Path | str | None,
        *,
        dataset_id: int,
        version_no: int,
    ) -> dict[str, Any]:
        if self.ingest_service is None:
            raise ValueError("ingest_service is required to ingest dataset versions")

        cleaned = Path(cleaned_path)
        chunk = None if chunk_path is None else Path(chunk_path)
        metadata = self.build_version_metadata(cleaned, chunk)
        counts, backend_status = await self.ingest_service.import_cleaned_knowledge(
            cleaned_path=cleaned,
            chunks_path=chunk,
        )
        persisted_version = self._create_dataset_version_record(
            dataset_id=dataset_id,
            version_no=version_no,
            metadata=metadata,
        )
        return {
            "metadata": metadata,
            "dataset_version": persisted_version,
            "counts": counts,
            "backend_status": backend_status,
        }

    def _create_dataset_version_record(
        self,
        *,
        dataset_id: int,
        version_no: int,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        repository = self.dataset_version_repository
        if repository is None:
            return None

        create_method = getattr(repository, "create_dataset_version", None)
        if create_method is None:
            create_method = getattr(repository, "create_version", None)
        if create_method is None:
            return None

        version = create_method(
            dataset_id=dataset_id,
            version_no=version_no,
            source_type=metadata["source_type"],
            source_uri=metadata["cleaned_path"],
            status="draft",
            document_count=metadata["document_count"],
            chunk_count=metadata["chunk_count"],
            metadata_json=metadata,
        )
        return self._serialize_dataset_version(version)

    def _serialize_dataset_version(self, version: Any) -> dict[str, Any]:
        if isinstance(version, dict):
            return version

        return {
            "id": getattr(version, "id", None),
            "dataset_id": getattr(version, "dataset_id", None),
            "version_no": getattr(version, "version_no", None),
            "source_type": getattr(version, "source_type", None),
            "source_uri": getattr(version, "source_uri", None),
            "status": getattr(version, "status", None),
            "document_count": getattr(version, "document_count", None),
            "chunk_count": getattr(version, "chunk_count", None),
            "metadata_json": getattr(version, "metadata_json", None),
        }

    def _serialize_dataset(self, dataset: Any) -> dict[str, Any]:
        if isinstance(dataset, dict):
            return dataset
        return {
            "id": getattr(dataset, "id", None),
            "code": getattr(dataset, "code", None),
            "name": getattr(dataset, "name", None),
            "knowledge_type": getattr(dataset, "knowledge_type", None),
            "description": getattr(dataset, "description", None),
        }
