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
        await case_collection.create_index([("eval_set_id", 1), ("validation_status", 1)])
        await case_collection.create_index([("eval_set_id", 1), ("category_l1", 1)])
        await case_collection.create_index([("eval_set_id", 1), ("eval_type", 1)])
        await case_collection.create_index([("eval_set_id", 1), ("difficulty", 1)])
        await self.mongo.db[self.collection("eval_runs")].create_index([("eval_set_id", 1), ("created_at", -1)])

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

    async def get_current_answers(self, faq_ids: list[str]) -> dict[str, str]:
        if not self.available() or not faq_ids:
            return {}
        cursor = self.mongo.db[self.collection("faq_items")].find({"id": {"$in": faq_ids}}, {"id": 1, "answer": 1, "answer_clean": 1})
        answers: dict[str, str] = {}
        async for doc in cursor:
            answers[str(doc.get("id"))] = str(doc.get("answer") or doc.get("answer_clean") or "")
        return answers

    async def update_stale_check_results(self, eval_set_id: str, results: list[Any]) -> None:
        if not self.available() or not results:
            return
        collection = self.mongo.db[self.collection("eval_cases")]
        for result in results:
            await collection.update_one(
                {"eval_set_id": eval_set_id, "case_id": result.case_id},
                {
                    "$set": {
                        "stale_status": result.status,
                        "stale_reason": result.reason,
                    }
                },
            )

    async def save_eval_run(self, run: dict[str, Any]) -> None:
        if not self.available():
            raise RuntimeError("MongoDB is unavailable")
        await self.mongo.db[self.collection("eval_runs")].update_one(
            {"_id": run["run_id"]},
            {"$set": {**run, "_id": run["run_id"]}},
            upsert=True,
        )

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
            .find({"eval_set_id": eval_set_id}, {"results": 0})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return [clean_doc(doc) async for doc in cursor]

    async def list_eval_run_results(self, run_id: str, page: int = 1, page_size: int = 20) -> tuple[list[dict[str, Any]], int]:
        run = await self.get_eval_run(run_id)
        if not run:
            return [], 0
        results = list(run.get("results") or [])
        start = (page - 1) * page_size
        return results[start : start + page_size], len(results)
