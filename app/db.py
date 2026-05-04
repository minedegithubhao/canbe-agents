from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.settings import get_settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Mongo:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client: Any | None = None
        self.db: Any | None = None
        self.status = "not_initialized"

    async def connect(self) -> None:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            self.client = AsyncIOMotorClient(self.settings.mongodb_uri, serverSelectionTimeoutMS=2000)
            await self.client.admin.command("ping")
            self.db = self.client[self.settings.mongodb_database]
            self.status = "ok"
        except Exception as exc:
            self.client = None
            self.db = None
            self.status = f"unavailable: {type(exc).__name__}: {exc}"

    async def close(self) -> None:
        if self.client is not None:
            self.client.close()

    def available(self) -> bool:
        return self.db is not None

    def collection(self, suffix: str) -> str:
        return f"{self.settings.project_prefix}_{suffix}"

    async def save_faq_items(self, items: list[dict[str, Any]]) -> int:
        if not self.available() or not items:
            return 0
        try:
            collection = self.db[self.collection("faq_items")]
            for item in items:
                item = dict(item)
                item["updatedAt"] = item.get("updatedAt") or utc_now()
                await collection.update_one(
                    {"id": item["id"]},
                    {"$set": item, "$setOnInsert": {"createdAt": utc_now()}},
                    upsert=True,
                )
            return len(items)
        except Exception as exc:
            self.status = f"unavailable: {type(exc).__name__}: {exc}"
            return 0

    async def save_chunks(self, chunks: list[dict[str, Any]]) -> int:
        if not self.available() or not chunks:
            return 0
        try:
            collection = self.db[self.collection("faq_chunks")]
            for chunk in chunks:
                chunk = dict(chunk)
                chunk["updatedAt"] = utc_now()
                await collection.update_one(
                    {"id": chunk["id"]},
                    {"$set": chunk, "$setOnInsert": {"createdAt": utc_now()}},
                    upsert=True,
                )
            return len(chunks)
        except Exception as exc:
            self.status = f"unavailable: {type(exc).__name__}: {exc}"
            return 0

    async def list_enabled_chunks(self, limit: int = 2000) -> list[dict[str, Any]]:
        if not self.available():
            return []
        try:
            cursor = self.db[self.collection("faq_chunks")].find({"enabled": {"$ne": False}}).limit(limit)
            return [clean_doc(doc) async for doc in cursor]
        except Exception as exc:
            self.status = f"unavailable: {type(exc).__name__}: {exc}"
            return []

    async def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        if not self.available() or not chunk_ids:
            return []
        try:
            cursor = self.db[self.collection("faq_chunks")].find({"id": {"$in": chunk_ids}})
            return [clean_doc(doc) async for doc in cursor]
        except Exception as exc:
            self.status = f"unavailable: {type(exc).__name__}: {exc}"
            return []

    async def get_faqs_by_ids(self, faq_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not self.available() or not faq_ids:
            return {}
        try:
            cursor = self.db[self.collection("faq_items")].find({"id": {"$in": faq_ids}})
            return {doc["id"]: clean_doc(doc) async for doc in cursor}
        except Exception as exc:
            self.status = f"unavailable: {type(exc).__name__}: {exc}"
            return {}

    async def get_faq_by_id(self, faq_id: str) -> dict[str, Any] | None:
        if not self.available() or not faq_id:
            return None
        try:
            doc = await self.db[self.collection("faq_items")].find_one({"id": faq_id})
            return clean_doc(doc) if doc else None
        except Exception as exc:
            self.status = f"unavailable: {type(exc).__name__}: {exc}"
            return None

    async def categories(self) -> list[dict[str, Any]]:
        if not self.available():
            return []
        try:
            pipeline = [
                {"$match": {"enabled": {"$ne": False}, "searchEnabled": {"$ne": False}, "status": "active"}},
                {"$group": {"_id": {"id": "$categoryL1", "name": "$categoryL1"}, "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ]
            rows: list[dict[str, Any]] = []
            async for row in self.db[self.collection("faq_items")].aggregate(pipeline):
                key = row.get("_id") or {}
                rows.append({"id": key.get("id") or "general", "name": key.get("name") or "FAQ", "count": row["count"]})
            return rows
        except Exception as exc:
            self.status = f"unavailable: {type(exc).__name__}: {exc}"
            return []

    async def hot_questions(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.available():
            return []
        try:
            cursor = (
                self.db[self.collection("faq_items")]
                .find({"enabled": {"$ne": False}, "searchEnabled": {"$ne": False}, "status": "active"})
                .sort([("priority", -1), ("updatedAt", -1)])
                .limit(limit)
            )
            return [clean_doc(doc) async for doc in cursor]
        except Exception as exc:
            self.status = f"unavailable: {type(exc).__name__}: {exc}"
            return []

    async def save_chat_log(self, log: dict[str, Any]) -> None:
        if not self.available():
            return
        try:
            log = dict(log)
            log["createdAt"] = utc_now()
            await self.db[self.collection("chat_logs")].insert_one(log)
        except Exception as exc:
            self.status = f"unavailable: {type(exc).__name__}: {exc}"

    async def save_feedback(self, feedback: dict[str, Any]) -> None:
        if not self.available():
            return
        try:
            feedback = dict(feedback)
            feedback["createdAt"] = utc_now()
            await self.db[self.collection("feedback_logs")].insert_one(feedback)
        except Exception as exc:
            self.status = f"unavailable: {type(exc).__name__}: {exc}"


class RedisStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client: Any | None = None
        self.status = "not_initialized"

    async def connect(self) -> None:
        try:
            from redis.asyncio import from_url

            self.client = from_url(self.settings.redis_url, decode_responses=True)
            await self.client.ping()
            self.status = "ok"
        except Exception as exc:
            self.client = None
            self.status = f"unavailable: {type(exc).__name__}: {exc}"

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()

    def key(self, suffix: str) -> str:
        return f"{self.settings.redis_prefix}:{suffix}"

    async def set_status(self, name: str, value: str, ttl: int = 3600) -> None:
        if self.client is not None:
            await self.client.set(self.key(f"status:{name}"), value, ex=ttl)

    async def set_json(self, suffix: str, value: dict[str, Any], ttl: int = 86400) -> None:
        if self.client is not None:
            await self.client.set(self.key(suffix), json.dumps(value, ensure_ascii=False), ex=ttl)

    async def get_json(self, suffix: str) -> dict[str, Any] | None:
        if self.client is None:
            return None
        raw = await self.client.get(self.key(suffix))
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None


class ElasticSearch:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client: Any | None = None
        self.status = "not_initialized"

    async def connect(self) -> None:
        try:
            from elasticsearch import AsyncElasticsearch

            kwargs: dict[str, Any] = {"hosts": [self.settings.elasticsearch_url], "request_timeout": 2}
            if self.settings.elasticsearch_username:
                kwargs["basic_auth"] = (self.settings.elasticsearch_username, self.settings.elasticsearch_password)
            self.client = AsyncElasticsearch(**kwargs)
            self.status = "ok" if await self.client.ping() else "unreachable"
        except Exception as exc:
            self.client = None
            self.status = f"unavailable: {type(exc).__name__}: {exc}"

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()

    def available(self) -> bool:
        return self.client is not None

    async def ensure_index(self) -> bool:
        if not self.available():
            return False
        index = self.settings.elasticsearch_index
        if await self.client.indices.exists(index=index):
            return True
        await self.client.indices.create(
            index=index,
            body={
                "mappings": {
                    "properties": {
                        "chunkId": {"type": "keyword"},
                        "faqId": {"type": "keyword"},
                        "question": {"type": "text", "analyzer": "standard"},
                        "rerankText": {"type": "text", "analyzer": "standard"},
                        "indexText": {"type": "text", "analyzer": "standard"},
                        "embeddingText": {"type": "text", "analyzer": "standard"},
                        "categoryL1": {"type": "keyword"},
                        "categoryL2": {"type": "keyword"},
                        "categoryL3": {"type": "keyword"},
                        "categoryPath": {"type": "keyword"},
                        "docType": {"type": "keyword"},
                        "status": {"type": "keyword"},
                        "searchEnabled": {"type": "boolean"},
                        "parentId": {"type": "keyword"},
                        "duplicateGroupId": {"type": "keyword"},
                        "sourceUrl": {"type": "keyword"},
                        "enabled": {"type": "boolean"},
                    }
                }
            },
        )
        return True

    async def index_chunks(self, chunks: list[dict[str, Any]]) -> int:
        if not self.available() or not chunks:
            return 0
        await self.ensure_index()
        for chunk in chunks:
            await self.client.index(
                index=self.settings.elasticsearch_index,
                id=chunk["id"],
                document={
                    "chunkId": chunk["id"],
                    "faqId": chunk["faqId"],
                    "question": chunk.get("question", ""),
                    "rerankText": chunk.get("rerankText", ""),
                    "indexText": chunk.get("indexText", ""),
                    "embeddingText": chunk.get("embeddingText", ""),
                    "categoryL1": chunk.get("categoryL1", ""),
                    "categoryL2": chunk.get("categoryL2", ""),
                    "categoryL3": chunk.get("categoryL3", ""),
                    "categoryPath": chunk.get("categoryPath", ""),
                    "docType": chunk.get("docType", ""),
                    "status": chunk.get("status", ""),
                    "searchEnabled": chunk.get("searchEnabled", True),
                    "parentId": chunk.get("parentId", ""),
                    "duplicateGroupId": chunk.get("duplicateGroupId", ""),
                    "sourceUrl": chunk.get("sourceUrl", ""),
                    "enabled": chunk.get("enabled", True),
                },
            )
        await self.client.indices.refresh(index=self.settings.elasticsearch_index)
        return len(chunks)

    async def keyword_search(
        self,
        query: str,
        top_k: int,
        *,
        allow_historical: bool = False,
        prefer_agreement: bool = False,
    ) -> list[dict[str, Any]]:
        if not self.available():
            return []
        filters: list[dict[str, Any]] = [{"term": {"enabled": True}}]
        if allow_historical:
            filters.append({"terms": {"docType": ["historical_rule", "policy_rule", "agreement", "faq", "operation_guide", "fee_standard", "service_intro"]}})
        else:
            filters.extend([{"term": {"searchEnabled": True}}, {"term": {"status": "active"}}])
        should = [{"term": {"docType": {"value": "agreement", "boost": 2.0}}}] if prefer_agreement else []
        body = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": [{"multi_match": {"query": query, "fields": ["question^3", "rerankText^2", "indexText"]}}],
                    "filter": filters,
                    "should": should,
                }
            },
        }
        try:
            response = await self.client.search(index=self.settings.elasticsearch_index, body=body)
        except Exception:
            return []
        return [
            {
                "chunkId": hit["_source"].get("chunkId") or hit["_id"],
                "faqId": hit["_source"].get("faqId"),
                "score": float(hit.get("_score") or 0.0),
                "source": "keyword",
            }
            for hit in response.get("hits", {}).get("hits", [])
        ]


class Milvus:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.status = "not_initialized"
        self.connected = False

    def available(self) -> bool:
        return self.connected

    async def connect(self) -> None:
        try:
            from pymilvus import connections, utility

            kwargs: dict[str, Any] = {"host": self.settings.milvus_host, "port": str(self.settings.milvus_port)}
            if self.settings.milvus_user:
                kwargs["user"] = self.settings.milvus_user
                kwargs["password"] = self.settings.milvus_password
            connections.connect(alias="default", **kwargs)
            utility.list_collections()
            self.connected = True
            self.status = "ok"
        except Exception as exc:
            self.connected = False
            self.status = f"unavailable: {type(exc).__name__}: {exc}"

    async def close(self) -> None:
        if not self.connected:
            return
        from pymilvus import connections

        connections.disconnect(alias="default")
        self.connected = False

    async def index_vectors(
        self,
        chunks: list[dict[str, Any]],
        vectors: list[list[float]],
        sparse_vectors: list[dict[int, float]],
    ) -> int:
        if not self.available() or not chunks or not vectors:
            return 0
        collection = self._ensure_collection()
        rows = [
            {
                "id": str(chunk["id"]),
                "chunk_id": str(chunk["id"]),
                "faq_id": str(chunk["faqId"]),
                "dense_vector": [float(value) for value in dense_vector],
                "sparse_vector": {int(key): float(value) for key, value in sparse_vector.items()},
            }
            for chunk, dense_vector, sparse_vector in zip(chunks, vectors, sparse_vectors)
        ]
        if hasattr(collection, "upsert"):
            collection.upsert(rows)
        else:
            collection.delete(self._in_expr("id", [row["id"] for row in rows]))
            collection.insert(rows)
        collection.flush()
        collection.load()
        return len(rows)

    async def dense_search(self, vector: list[float], top_k: int) -> list[dict[str, Any]]:
        return await self._search("dense_vector", [float(value) for value in vector], top_k, "dense", "COSINE")

    async def sparse_search(self, sparse_vector: dict[int, float], top_k: int) -> list[dict[str, Any]]:
        return await self._search("sparse_vector", {int(k): float(v) for k, v in sparse_vector.items()}, top_k, "sparse", "IP")

    async def _search(self, field: str, vector: Any, top_k: int, source: str, metric: str) -> list[dict[str, Any]]:
        if not self.available():
            return []
        try:
            collection = self._ensure_collection()
            collection.load()
            results = collection.search(
                data=[vector],
                anns_field=field,
                param={"metric_type": metric, "params": {"ef": 64} if field == "dense_vector" else {}},
                limit=top_k,
                output_fields=["chunk_id", "faq_id"],
            )
            return hits_to_dicts(results[0], source)
        except Exception as exc:
            self.status = f"unavailable: {type(exc).__name__}: {exc}"
            return []

    def _ensure_collection(self):
        from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, utility

        name = self.settings.milvus_collection
        if utility.has_collection(name):
            collection = Collection(name)
            field_names = {field.name for field in collection.schema.fields}
            if {"id", "chunk_id", "faq_id", "dense_vector", "sparse_vector"}.issubset(field_names):
                ensure_indexes(collection)
                return collection
            utility.drop_collection(name)
        collection = Collection(
            name=name,
            schema=CollectionSchema(
                fields=[
                    FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
                    FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=128),
                    FieldSchema(name="faq_id", dtype=DataType.VARCHAR, max_length=128),
                    FieldSchema(name="dense_vector", dtype=DataType.FLOAT_VECTOR, dim=self.settings.bailian_embedding_dimension),
                    FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR),
                ],
                description="JD help FAQ vectors",
            ),
        )
        ensure_indexes(collection)
        return collection

    @staticmethod
    def _in_expr(field: str, values: list[str]) -> str:
        quoted = [f'"{value.replace("\\", "\\\\").replace(chr(34), "\\\"")}"' for value in values]
        return f'{field} in [{", ".join(quoted)}]'


def clean_doc(doc: dict[str, Any]) -> dict[str, Any]:
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


def ensure_indexes(collection: Any) -> None:
    existing = {index.field_name for index in collection.indexes}
    if "dense_vector" not in existing:
        collection.create_index(
            field_name="dense_vector",
            index_params={"index_type": "HNSW", "metric_type": "COSINE", "params": {"M": 16, "efConstruction": 200}},
        )
    if "sparse_vector" not in existing:
        collection.create_index(
            field_name="sparse_vector",
            index_params={"index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP", "params": {}},
        )


def hits_to_dicts(hits: Any, source: str) -> list[dict[str, Any]]:
    return [
        {
            "chunkId": hit.entity.get("chunk_id"),
            "faqId": hit.entity.get("faq_id"),
            "score": float(hit.score),
            "source": source,
        }
        for hit in hits
    ]


def sparse_from_text(text: str) -> dict[int, float]:
    weights: dict[int, float] = {}
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    tokens = [word for word in normalized.split() if word]
    tokens.extend(char for char in text if "\u4e00" <= char <= "\u9fff")
    for token in tokens:
        index = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big") % 30000
        weights[index] = weights.get(index, 0.0) + 1.0
    return weights
