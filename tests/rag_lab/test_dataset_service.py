from pathlib import Path

import pytest

from app.services.dataset_service import DatasetService
from app.services.ingest_service import IngestService


def test_dataset_service_builds_version_from_clean_jsonl(tmp_path: Path):
    cleaned = tmp_path / "cleaned.jsonl"
    cleaned.write_text('{"id":"1","question":"q","answer":"a"}\n', encoding="utf-8")

    service = DatasetService(None, None, None)

    summary = service.inspect_sources(cleaned, None)

    assert summary["document_count"] == 1


@pytest.mark.asyncio
async def test_dataset_service_ingest_version_persists_dataset_version(tmp_path: Path):
    class StubDatasetVersionRepository:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def create_dataset_version(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "id": 42,
                "dataset_id": kwargs["dataset_id"],
                "version_no": kwargs["version_no"],
                "status": kwargs["status"],
                "document_count": kwargs["document_count"],
                "chunk_count": kwargs["chunk_count"],
                "metadata_json": kwargs["metadata_json"],
            }

    class StubMongo:
        status = "completed"

        def __init__(self) -> None:
            self.saved_faq_docs: list[dict] = []
            self.saved_chunk_docs: list[dict] = []

        async def save_faq_items(self, docs):
            self.saved_faq_docs = list(docs)
            return len(self.saved_faq_docs)

        async def save_chunks(self, docs):
            self.saved_chunk_docs = list(docs)
            return len(self.saved_chunk_docs)

    cleaned = tmp_path / "cleaned.jsonl"
    default_chunks = tmp_path / "default.chunks.jsonl"
    cleaned.write_text('{"id":"1","question":"q","answer":"a"}\n', encoding="utf-8")
    default_chunks.write_text(
        '{"id":"c1","parent_id":"1","chunk_text":"body","question":"q"}\n',
        encoding="utf-8",
    )

    version_repo = StubDatasetVersionRepository()
    mongo = StubMongo()
    ingest_service = IngestService(
        mongo=mongo,
        milvus=None,
        es=None,
        redis=None,
        embedder=None,
    )
    ingest_service.settings.jd_help_cleaned_jsonl_path = tmp_path / "unused.cleaned.jsonl"
    ingest_service.settings.jd_help_chunks_jsonl_path = default_chunks
    service = DatasetService(
        dataset_repository=None,
        dataset_version_repository=version_repo,
        ingest_service=ingest_service,
    )

    dataset_id = 123
    version_no = 7

    result = await service.ingest_version(
        cleaned,
        None,
        dataset_id=dataset_id,
        version_no=version_no,
    )

    assert version_repo.calls == [
        {
            "dataset_id": dataset_id,
            "version_no": version_no,
            "source_type": "jsonl",
            "source_uri": str(cleaned),
            "status": "draft",
            "document_count": 1,
            "chunk_count": 0,
            "metadata_json": {
                "source_type": "jsonl",
                "cleaned_path": str(cleaned),
                "chunk_path": None,
                "document_count": 1,
                "chunk_count": 0,
            },
        }
    ]
    assert result["dataset_version"]["id"] == 42
    assert result["dataset_version"]["metadata_json"]["chunk_count"] == 0
    assert result["counts"]["faqItems"] == 1
    assert result["counts"]["faqChunks"] == 0
    assert result["counts"]["sourceChunks"] == 0
    assert mongo.saved_chunk_docs == []
