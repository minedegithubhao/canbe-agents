from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.retrieval_service import Embedder, QueryProcessor
from app.settings import get_settings

_USE_DEFAULT_CHUNKS = object()


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IngestService:
    """知识导入与索引构建服务。

    导入链路和问答链路是 RAG 的两条主干：
    导入链路把清洗后的 FAQ 转成统一存储结构，并构建关键词/向量索引；
    问答链路再基于这些索引召回证据。
    """

    def __init__(self, mongo: Any, milvus: Any, es: Any, redis: Any, embedder: Embedder) -> None:
        self.settings = get_settings()
        self.mongo = mongo
        self.milvus = milvus
        self.es = es
        self.redis = redis
        self.embedder = embedder
        self.query_processor = QueryProcessor()

    async def import_cleaned_knowledge(
        self,
        cleaned_path: Path | None = None,
        chunks_path: Path | None | object = _USE_DEFAULT_CHUNKS,
    ) -> tuple[dict[str, int], dict[str, str]]:
        """把离线清洗产物写入 Mongo。

        FAQ item 是可展示的完整问答；chunk 是用于检索的片段。
        这种拆分让召回粒度更细，同时回答阶段仍能回到完整 FAQ 元数据。
        """
        await self.set_status("import", "running")
        faq_rows = load_jsonl(cleaned_path or self.settings.jd_help_cleaned_jsonl_path)
        if chunks_path is _USE_DEFAULT_CHUNKS:
            chunk_rows = load_jsonl(self.settings.jd_help_chunks_jsonl_path)
        else:
            chunk_rows = [] if chunks_path is None else load_jsonl(chunks_path)
        saved_faqs = await self.mongo.save_faq_items([self.faq_to_doc(row) for row in faq_rows])
        saved_chunks = await self.mongo.save_chunks([self.chunk_to_doc(row) for row in chunk_rows])
        await self.set_status("import", "completed")
        return (
            {"faqItems": saved_faqs, "faqChunks": saved_chunks, "sourceFaqItems": len(faq_rows), "sourceChunks": len(chunk_rows)},
            {"mongodb": self.mongo.status, "redis": component_status(self.redis)},
        )

    async def start_import_task(self) -> dict[str, Any]:
        task_id = f"imp_{uuid.uuid4().hex}"
        task = task_payload(task_id, "running", "queued", "import")
        task["source"] = "cleaned_jsonl"
        await self.set_task_payload(task_id, task)
        await self.set_status("import", task_id)
        asyncio.create_task(self.run_import_task(task_id))
        return task

    async def run_import_task(self, task_id: str) -> None:
        try:
            await self.set_task(task_id, status="running", stage="importing_cleaned_jsonl", progress=5)
            counts, backend_status = await self.import_cleaned_knowledge()
            await self.set_task(task_id, status="completed", stage="completed", progress=100, counts=counts, backendStatus=backend_status, finishedAt=utc_iso())
        except Exception as exc:
            await self.set_task(task_id, status="failed", stage="failed", error=f"{type(exc).__name__}: {exc}", finishedAt=utc_iso())

    async def start_build_index_task(self) -> dict[str, Any]:
        task_id = f"idx_{uuid.uuid4().hex}"
        task = task_payload(task_id, "running", "queued", "build_index")
        await self.set_task_payload(task_id, task)
        await self.set_status("build_index", task_id)
        asyncio.create_task(self.run_build_index_task(task_id))
        return task

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        return None if not self.redis else await self.redis.get_json(task_key(task_id))

    async def run_build_index_task(self, task_id: str) -> None:
        try:
            await self.set_task(task_id, status="running", stage="loading_chunks")
            counts, backend_status = await self.build_index(task_id)
            await self.set_task(task_id, status="completed", stage="completed", progress=100, counts=counts, backendStatus=backend_status, finishedAt=utc_iso())
        except Exception as exc:
            await self.set_task(task_id, status="failed", stage="failed", error=f"{type(exc).__name__}: {exc}", finishedAt=utc_iso())

    async def build_index(self, task_id: str | None = None) -> tuple[dict[str, int], dict[str, str]]:
        """为已导入 chunk 构建检索索引。

        Elasticsearch 保存关键词索引；Milvus 同时保存 dense 和 sparse 向量。
        三者对应 Retriever 中的 keyword、dense、sparse 三路召回。
        """
        chunks = await self.mongo.list_enabled_chunks()
        if task_id:
            await self.set_task(task_id, stage="indexing_elasticsearch", totalChunks=len(chunks), progress=10)
        es_count = await self.es.index_chunks(chunks)
        if task_id:
            await self.set_task(task_id, stage="encoding_dense_vectors", elasticsearchIndexed=es_count, progress=35)
        dense_vectors = await self.encode_dense(chunks, task_id)
        if task_id:
            await self.set_task(task_id, stage="encoding_sparse_vectors", encodedVectors=len(dense_vectors), progress=80)
        sparse_vectors = await self.encode_sparse(chunks, task_id)
        if task_id:
            await self.set_task(task_id, stage="indexing_milvus", encodedSparseVectors=len(sparse_vectors), progress=90)
        milvus_count = await self.milvus.index_vectors(chunks, dense_vectors, sparse_vectors)
        return (
            {"chunks": len(chunks), "elasticsearchIndexed": es_count, "milvusIndexed": milvus_count},
            {"mongodb": self.mongo.status, "elasticsearch": self.es.status, "milvus": self.milvus.status, "redis": component_status(self.redis), "embedder": self.embedder.status},
        )

    async def encode_dense(self, chunks: list[dict[str, Any]], task_id: str | None) -> list[list[float]]:
        """批量生成 dense embedding。

        embeddingText 优先于 indexText：前者通常更干净，适合语义向量；
        后者包含更多检索增强词，适合关键词和稀疏检索。
        """
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), self.settings.bailian_embedding_batch_size):
            batch = chunks[start : start + self.settings.bailian_embedding_batch_size]
            vectors.extend(await asyncio.to_thread(self.embedder.encode_dense, [str(chunk.get("embeddingText") or chunk.get("indexText") or "") for chunk in batch]))
            if task_id and chunks:
                await self.set_task(task_id, encodedVectors=min(start + len(batch), len(chunks)), progress=35 + int((min(start + len(batch), len(chunks)) / len(chunks)) * 45))
            await asyncio.sleep(0)
        return vectors

    async def encode_sparse(self, chunks: list[dict[str, Any]], task_id: str | None) -> list[dict[int, float]]:
        """批量生成 sparse 向量，保留 indexText 中的词面增强信息。"""
        vectors: list[dict[int, float]] = []
        for start in range(0, len(chunks), self.settings.bailian_embedding_batch_size):
            batch = chunks[start : start + self.settings.bailian_embedding_batch_size]
            vectors.extend(await asyncio.to_thread(self.embedder.encode_sparse, [str(chunk.get("indexText") or chunk.get("embeddingText") or "") for chunk in batch]))
            if task_id and chunks:
                await self.set_task(task_id, encodedSparseVectors=min(start + len(batch), len(chunks)), progress=80 + int((min(start + len(batch), len(chunks)) / len(chunks)) * 10))
            await asyncio.sleep(0)
        return vectors

    async def set_task(self, task_id: str, **updates: Any) -> None:
        payload = await self.get_task(task_id) or task_payload(task_id, "running", "unknown", "import" if task_id.startswith("imp_") else "build_index")
        payload.update(updates)
        payload["updatedAt"] = utc_iso()
        await self.set_task_payload(task_id, payload)

    async def set_task_payload(self, task_id: str, payload: dict[str, Any]) -> None:
        if self.redis:
            await self.redis.set_json(task_key(task_id), payload)

    async def set_status(self, name: str, value: str) -> None:
        if self.redis:
            await self.redis.set_status(name, value)

    def faq_to_doc(self, row: dict[str, Any]) -> dict[str, Any]:
        """把清洗后的 FAQ 行映射为 Mongo 中的主文档。

        这里会补充同义词、分类、边界、优先级和质量标记。
        后续 ChatService 返回来源时主要依赖这个文档。
        """
        canonical_terms, synonym_terms = self.query_processor.terms_for_text(" ".join(str(row.get(key) or "") for key in ("category_path", "question", "answer_clean", "index_text")))
        answer = row.get("answer_clean") or row.get("answer_raw") or ""
        index_text = row.get("index_text") or " ".join(str(value or "") for value in [row.get("category_path"), row.get("question"), answer, f"source_url:{row.get('url') or ''}"] if value)
        return {
            "id": row["id"],
            "question": row.get("question", ""),
            "similarQuestions": row.get("similar_questions") or [],
            "answer": answer,
            "answerRaw": row.get("answer_raw", ""),
            "embeddingText": row.get("embedding_text") or fallback_embedding(row.get("category_path") or "", row.get("question") or "", answer),
            "indexText": append_terms(index_text, canonical_terms, synonym_terms),
            "category": row.get("category_l1") or "general",
            "categoryName": row.get("category_path") or row.get("category_l3") or "FAQ",
            "categoryL1": row.get("category_l1") or "",
            "categoryL2": row.get("category_l2") or "",
            "categoryL3": row.get("category_l3") or "",
            "categoryPath": row.get("category_path") or "",
            "docType": row.get("doc_type") or "faq",
            "status": row.get("status") or "active",
            "searchEnabled": bool(row.get("search_enabled", True)),
            "source": "京东帮助中心公开 FAQ",
            "sourceUrl": row.get("url") or "",
            "sourceTitle": "京东帮助中心",
            "enabled": True,
            "priority": priority_for_doc_type(str(row.get("doc_type") or "faq")),
            "riskLevel": "low",
            "answerBoundary": "只基于公开帮助文档回答，不查询个人状态",
            "updatedAt": utc_iso(),
            "fetchedAt": row.get("exported_at") or utc_iso(),
            "contentHash": row.get("content_hash") or sha256(str(row)),
            "suggestedQuestions": [],
            "canonicalTerms": canonical_terms,
            "synonymTerms": synonym_terms,
            "pageDate": row.get("page_date"),
            "effectiveDate": row.get("effective_date"),
            "expiredDate": row.get("expired_date"),
            "parentId": row.get("parent_id"),
            "sectionPath": row.get("section_path"),
            "duplicateGroupId": row.get("duplicate_group_id"),
            "duplicateOf": row.get("duplicate_of"),
            "qualityFlags": row.get("quality_flags") or [],
            "hasImageReference": row.get("has_image_reference", False),
            "imageMissing": row.get("image_missing", False),
        }

    def chunk_to_doc(self, row: dict[str, Any]) -> dict[str, Any]:
        """把清洗后的 chunk 行映射为检索文档。

        chunk 文档面向召回和重排：embeddingText 给 dense，indexText 给 keyword/sparse，
        rerankText 则把问题、章节和片段整理成重排模型更容易判断的证据文本。
        """
        canonical_terms, synonym_terms = self.query_processor.terms_for_text(" ".join(str(row.get(key) or "") for key in ("category_l1", "category_l2", "category_l3", "question", "chunk_text", "index_text")))
        category_path = " > ".join(item for item in [row.get("category_l1"), row.get("category_l2"), row.get("category_l3")] if item)
        chunk_text = row.get("chunk_text") or ""
        index_text = row.get("index_text") or " ".join(str(value or "") for value in [category_path, row.get("question"), chunk_text, f"source_url:{row.get('url') or ''}"] if value)
        return {
            "id": row["id"],
            "faqId": row.get("parent_id") or row.get("faq_id") or "",
            "parentId": row.get("parent_id") or row.get("faq_id") or "",
            "chunkIndex": int(row.get("chunk_index") or 0),
            "chunkText": chunk_text,
            "chunkTitle": row.get("chunk_title") or row.get("question") or "",
            "question": row.get("question") or "",
            "embeddingText": row.get("embedding_text") or fallback_embedding(category_path, row.get("question") or "", chunk_text),
            "indexText": append_terms(index_text, canonical_terms, synonym_terms),
            "rerankText": rerank_text(row),
            "sourceUrl": row.get("url") or "",
            "category": row.get("category_l1") or "general",
            "categoryL1": row.get("category_l1") or "",
            "categoryL2": row.get("category_l2") or "",
            "categoryL3": row.get("category_l3") or "",
            "categoryPath": category_path,
            "docType": row.get("doc_type") or "faq",
            "status": row.get("status") or "active",
            "searchEnabled": bool(row.get("search_enabled", True)),
            "enabled": True,
            "qualityFlags": row.get("quality_flags") or [],
            "canonicalTerms": canonical_terms,
            "synonymTerms": synonym_terms,
            "contentHash": sha256(f"{row.get('id')}|{row.get('parent_id')}|{row.get('chunk_text')}|{row.get('index_text')}"),
        }

    _cleaned_faq_to_storage_dict = faq_to_doc
    _cleaned_chunk_to_storage_dict = chunk_to_doc

    @staticmethod
    def load_source_rows(
        cleaned_path: Path,
        chunks_path: Path | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        faq_rows = load_jsonl(cleaned_path)
        chunk_rows = [] if chunks_path is None else load_jsonl(chunks_path)
        return faq_rows, chunk_rows


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def task_payload(task_id: str, status: str, stage: str, task_type: str) -> dict[str, Any]:
    now = utc_iso()
    return {"taskId": task_id, "type": task_type, "status": status, "stage": stage, "progress": 0, "counts": {}, "backendStatus": {}, "error": "", "createdAt": now, "updatedAt": now}


def task_key(task_id: str) -> str:
    return f'{"import" if task_id.startswith("imp_") else "index"}:task:{task_id}'


def append_terms(text: str, canonical_terms: list[str], synonym_terms: list[str]) -> str:
    return text or "" if not canonical_terms and not synonym_terms else f"{text or ''} canonical_terms:{' '.join(canonical_terms)} synonym_terms:{' '.join(synonym_terms)}"


def rerank_text(row: dict[str, Any]) -> str:
    return "\n".join(part for part in [f"问题：{row.get('question') or ''}", f"章节：{row.get('chunk_title') or ''}", f"答案片段：{row.get('chunk_text') or ''}"] if part.strip())


def fallback_embedding(category_path: str, question: str, answer: str) -> str:
    return "\n".join(part for part in [category_path, f"问题：{question}" if question else "", f"答案：{answer}" if answer else ""] if part.strip())


def priority_for_doc_type(doc_type: str) -> int:
    return 20 if doc_type in {"operation_guide", "fee_standard"} else 10 if doc_type == "faq" else 0


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def component_status(component: Any) -> str:
    return str(getattr(component, "status", "not_configured"))
