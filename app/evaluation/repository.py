from __future__ import annotations

from typing import Any

from app.evaluation.schemas import GeneratedEvalSet
from app.repositories.storage import clean_doc


class EvalSetRepository:
    def __init__(self, mongo: Any) -> None:
        self.mongo = mongo

    def available(self) -> bool:
        return bool(self.mongo and self.mongo.available())

    def collection(self, suffix: str) -> str:
        return self.mongo.collection(suffix)

    async def ensure_indexes(self) -> None:
        if not self.available():
            return
        await self.mongo.db[self.collection("eval_sets")].create_index([("created_at", -1)])
        case_collection = self.mongo.db[self.collection("eval_cases")]
        await case_collection.create_index([("eval_set_id", 1), ("case_id", 1)], unique=True)
        await case_collection.create_index([("eval_set_id", 1), ("category", 1)])
        await case_collection.create_index([("eval_set_id", 1), ("eval_type", 1)])
        await case_collection.create_index([("eval_set_id", 1), ("difficulty", 1)])
        await case_collection.create_index([("eval_set_id", 1), ("question_style", 1)])
        await self.mongo.db[self.collection("eval_runs")].create_index([("eval_set_id", 1), ("created_at", -1)])
        result_collection = self.mongo.db[self.collection("eval_run_results")]
        await result_collection.create_index([("run_id", 1), ("case_id", 1)], unique=True)
        await result_collection.create_index([("run_id", 1), ("metrics.hit_at_k", 1)])
        await result_collection.create_index([("run_id", 1), ("metrics.context_recall_at_k", 1)])
        await result_collection.create_index([("run_id", 1), ("diagnostics.effective_k", 1)])

    async def save_generated_eval_set(self, generated: GeneratedEvalSet) -> None:
        if not self.available():
            raise RuntimeError("MongoDB is unavailable")
        eval_set_doc = {
            "_id": generated.eval_set_id,
            "eval_set_id": generated.eval_set_id,
            "name": generated.name,
            "status": "ready",
            "source_path": generated.source_path,
            "source_hash": generated.source_hash,
            "created_at": generated.created_at,
            "created_by": generated.created_by,
            "config": generated.config,
            "summary": generated.summary,
        }
        await self.mongo.db[self.collection("eval_sets")].update_one(
            {"_id": generated.eval_set_id},
            {"$set": eval_set_doc},
            upsert=True,
        )
        case_collection = self.mongo.db[self.collection("eval_cases")]
        for case in generated.cases:
            case_doc = case.model_dump(mode="json")
            case_doc["_id"] = f"{generated.eval_set_id}:{case.case_id}"
            case_doc["eval_set_id"] = generated.eval_set_id
            await case_collection.update_one(
                {"eval_set_id": generated.eval_set_id, "case_id": case.case_id},
                {"$set": case_doc},
                upsert=True,
            )

    async def list_eval_sets(self, limit: int = 50, skip: int = 0) -> list[dict[str, Any]]:
        if not self.available():
            return []
        cursor = self.mongo.db[self.collection("eval_sets")].find({}).sort("created_at", -1).skip(skip).limit(limit)
        return [clean_doc(doc) async for doc in cursor]

    async def get_eval_set(self, eval_set_id: str) -> dict[str, Any] | None:
        if not self.available():
            return None
        doc = await self.mongo.db[self.collection("eval_sets")].find_one({"_id": eval_set_id})
        return clean_doc(doc) if doc else None

    async def delete_eval_set(self, eval_set_id: str) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("MongoDB is unavailable")
        run_collection = self.mongo.db[self.collection("eval_runs")]
        run_ids = [doc["run_id"] async for doc in run_collection.find({"eval_set_id": eval_set_id}, {"run_id": 1})]
        result_collection = self.mongo.db[self.collection("eval_run_results")]
        result_delete = await result_collection.delete_many({"run_id": {"$in": run_ids}}) if run_ids else None
        run_delete = await run_collection.delete_many({"eval_set_id": eval_set_id})
        case_delete = await self.mongo.db[self.collection("eval_cases")].delete_many({"eval_set_id": eval_set_id})
        eval_set_delete = await self.mongo.db[self.collection("eval_sets")].delete_one({"_id": eval_set_id})
        return {
            "ok": eval_set_delete.deleted_count > 0,
            "eval_set_id": eval_set_id,
            "deleted_eval_sets": eval_set_delete.deleted_count,
            "deleted_cases": case_delete.deleted_count,
            "deleted_runs": run_delete.deleted_count,
            "deleted_run_results": result_delete.deleted_count if result_delete else 0,
        }

    async def list_cases(
        self,
        eval_set_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if not self.available():
            return [], 0
        query: dict[str, Any] = {"eval_set_id": eval_set_id}
        for key, value in (filters or {}).items():
            if value:
                query[key] = value
        collection = self.mongo.db[self.collection("eval_cases")]
        total = await collection.count_documents(query)
        cursor = collection.find(query).sort("case_id", 1).skip((page - 1) * page_size).limit(page_size)
        return [clean_doc(doc) async for doc in cursor], total

    async def save_eval_run(self, run: dict[str, Any]) -> None:
        if not self.available():
            raise RuntimeError("MongoDB is unavailable")
        await self.mongo.db[self.collection("eval_runs")].update_one(
            {"_id": run["run_id"]},
            {"$set": {**run, "_id": run["run_id"]}},
            upsert=True,
        )

    async def update_eval_run(self, run_id: str, patch: dict[str, Any]) -> None:
        if not self.available():
            raise RuntimeError("MongoDB is unavailable")
        await self.mongo.db[self.collection("eval_runs")].update_one(
            {"_id": run_id},
            {"$set": patch},
        )

    async def save_eval_run_results(self, run_id: str, results: list[dict[str, Any]]) -> None:
        if not self.available():
            raise RuntimeError("MongoDB is unavailable")
        collection = self.mongo.db[self.collection("eval_run_results")]
        for result in results:
            result_doc = {**result, "_id": result.get("_id") or f"{run_id}:{result['case_id']}", "run_id": run_id}
            await collection.update_one(
                {"run_id": run_id, "case_id": result["case_id"]},
                {"$set": result_doc},
                upsert=True,
            )

    async def replace_eval_run_results(self, run_id: str, results: list[dict[str, Any]]) -> None:
        if not self.available():
            raise RuntimeError("MongoDB is unavailable")
        collection = self.mongo.db[self.collection("eval_run_results")]
        await collection.delete_many({"run_id": run_id})
        await self.save_eval_run_results(run_id, results)

    async def get_eval_run(self, run_id: str) -> dict[str, Any] | None:
        if not self.available():
            return None
        doc = await self.mongo.db[self.collection("eval_runs")].find_one({"_id": run_id})
        return clean_doc(doc) if doc else None

    async def list_eval_runs(self, eval_set_id: str, limit: int = 50, skip: int = 0) -> list[dict[str, Any]]:
        if not self.available():
            return []
        cursor = (
            self.mongo.db[self.collection("eval_runs")]
            .find({"eval_set_id": eval_set_id})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return [clean_doc(doc) async for doc in cursor]

    async def list_eval_run_results(
        self,
        run_id: str,
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if not self.available():
            return [], 0
        query: dict[str, Any] = {"run_id": run_id}
        for key, value in (filters or {}).items():
            if value:
                query[key] = value
        collection = self.mongo.db[self.collection("eval_run_results")]
        total = await collection.count_documents(query)
        cursor = collection.find(query).sort("case_id", 1).skip((page - 1) * page_size).limit(page_size)
        return [clean_doc(doc) async for doc in cursor], total
