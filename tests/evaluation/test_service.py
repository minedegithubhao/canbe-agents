from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.evaluation.schemas import EvalRunConfig, EvalSetGenerateRequest
from app.evaluation.service import EvaluationService, EvalSourceChangedError


class FakeEvalRepository:
    def __init__(self) -> None:
        self.eval_sets: dict[str, dict] = {}
        self.eval_cases: list[dict] = []
        self.eval_runs: dict[str, dict] = {}
        self.eval_run_results: dict[str, list[dict]] = {}
        self.run_updates: list[dict] = []
        self.saved_result_batches: list[list[dict]] = []

    async def save_generated_eval_set(self, generated):
        self.eval_sets[generated.eval_set_id] = {
            "_id": generated.eval_set_id,
            "eval_set_id": generated.eval_set_id,
            "name": generated.name,
            "summary": generated.summary,
            "source_path": generated.source_path,
            "source_hash": generated.source_hash,
            "config": generated.config,
        }
        self.eval_cases.extend(
            dict(case.model_dump(mode="json"), eval_set_id=generated.eval_set_id, _id=f"{generated.eval_set_id}:{case.case_id}")
            for case in generated.cases
        )

    async def list_eval_sets(self, limit: int = 50, skip: int = 0):
        return list(self.eval_sets.values())[skip : skip + limit]

    async def get_eval_set(self, eval_set_id: str):
        return self.eval_sets.get(eval_set_id)

    async def list_cases(self, eval_set_id: str, *, page: int = 1, page_size: int = 20, filters=None):
        filters = filters or {}
        rows = [case for case in self.eval_cases if case["eval_set_id"] == eval_set_id]
        for key, value in filters.items():
            if value:
                rows = [case for case in rows if case.get(key) == value]
        start = (page - 1) * page_size
        return rows[start : start + page_size], len(rows)

    async def save_eval_run(self, run):
        self.eval_runs[run["run_id"]] = run

    async def update_eval_run(self, run_id: str, patch: dict):
        self.eval_runs[run_id].update(patch)
        self.run_updates.append({"run_id": run_id, **patch})

    async def save_eval_run_results(self, run_id: str, results: list[dict]):
        self.saved_result_batches.append(results)
        existing = list(self.eval_run_results.get(run_id) or [])
        merged = {
            item["case_id"]: item
            for item in [*existing, *results]
        }
        self.eval_run_results[run_id] = list(merged.values())

    async def replace_eval_run_results(self, run_id: str, results: list[dict]):
        self.saved_result_batches.append(results)
        self.eval_run_results[run_id] = results

    async def get_eval_run(self, run_id: str):
        return self.eval_runs.get(run_id)

    async def list_eval_runs(self, eval_set_id: str, limit: int = 50, skip: int = 0):
        rows = [run for run in self.eval_runs.values() if run["eval_set_id"] == eval_set_id]
        return rows[skip : skip + limit]

    async def list_eval_run_results(self, run_id: str, page: int = 1, page_size: int = 20, filters=None):
        rows = list(self.eval_run_results.get(run_id) or [])
        start = (page - 1) * page_size
        return rows[start : start + page_size], len(rows)

    async def delete_eval_set(self, eval_set_id: str):
        existed = 1 if self.eval_sets.pop(eval_set_id, None) else 0
        deleted_cases = len([case for case in self.eval_cases if case["eval_set_id"] == eval_set_id])
        self.eval_cases = [case for case in self.eval_cases if case["eval_set_id"] != eval_set_id]
        run_ids = [run_id for run_id, run in self.eval_runs.items() if run["eval_set_id"] == eval_set_id]
        deleted_runs = len(run_ids)
        for run_id in run_ids:
            self.eval_runs.pop(run_id, None)
        deleted_results = 0
        for run_id in run_ids:
            deleted_results += len(self.eval_run_results.pop(run_id, []))
        return {
            "ok": bool(existed),
            "eval_set_id": eval_set_id,
            "deleted_eval_sets": existed,
            "deleted_cases": deleted_cases,
            "deleted_runs": deleted_runs,
            "deleted_run_results": deleted_results,
        }


@dataclass
class FakeCandidate:
    chunk_id: str
    faq_id: str
    final_score: float
    chunk: dict
    faq: dict


class FakeRetriever:
    async def retrieve(self, query: str, top_k: int | None = None):
        return [
            FakeCandidate(
                chunk_id="noise_chunk",
                faq_id="FAQ_noise",
                final_score=0.8,
                chunk={"chunkText": "物流信息通常在 24 小时内更新。", "sourceUrl": "https://help.jd.com/user/issue/noise.html"},
                faq={"sourceUrl": "https://help.jd.com/user/issue/noise.html"},
            ),
            FakeCandidate(
                chunk_id="chunk_1",
                faq_id="FAQ_1",
                final_score=0.76,
                chunk={"chunkText": "订单未支付可取消重拍。", "sourceUrl": "https://help.jd.com/user/issue/FAQ_1.html"},
                faq={"sourceUrl": "https://help.jd.com/user/issue/FAQ_1.html"},
            ),
        ], {"degraded": False}


class EmptyRetriever:
    async def retrieve(self, query: str, top_k: int | None = None):
        return [], {"degraded": False}


class ConcurrentTrackingRetriever:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self._lock = asyncio.Lock()

    async def retrieve(self, query: str, top_k: int | None = None):
        async with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.05)
            chunk_id = query.replace("问题", "chunk_")
            faq_id = query.replace("问题", "FAQ_")
            return [
                FakeCandidate(
                    chunk_id=chunk_id,
                    faq_id=faq_id,
                    final_score=0.9,
                    chunk={"chunkText": f"{query} 对应答案", "sourceUrl": f"https://help.jd.com/{chunk_id}.html"},
                    faq={"sourceUrl": f"https://help.jd.com/{faq_id}.html"},
                )
            ], {"degraded": False}
        finally:
            async with self._lock:
                self.active -= 1


@pytest.mark.asyncio
async def test_service_generates_and_saves_eval_set(tmp_path: Path):
    source_path = write_chunk_jsonl(tmp_path)
    service = EvaluationService(repository=FakeEvalRepository(), retriever=FakeRetriever())

    response = await service.generate(EvalSetGenerateRequest(name="smoke", total_count=1, source_path=str(source_path)))

    assert response["ok"] is True
    assert response["eval_set_id"].startswith("eval_")
    assert response["summary"] == {"total": 1}
    stored_cases, total = await service.list_cases(response["eval_set_id"])
    assert total == 1
    assert stored_cases[0]["expected_retrieved_chunk_ids"] == ["chunk_1"]


@pytest.mark.asyncio
async def test_service_list_eval_sets_filters_legacy_faq_eval_sets():
    repository = FakeEvalRepository()
    repository.eval_sets = {
        "eval_chunk": {
            "eval_set_id": "eval_chunk",
            "name": "chunk eval",
            "config": {"eval_type_distribution": {"single_chunk": 0.7, "multi_chunk": 0.3}},
        },
        "eval_legacy": {
            "eval_set_id": "eval_legacy",
            "name": "legacy faq eval",
            "config": {"eval_type_distribution": {"single_faq_equivalent": 1.0}},
        },
        "eval_missing_config": {
            "eval_set_id": "eval_missing_config",
            "name": "old eval without config",
            "config": {},
        },
    }
    service = EvaluationService(repository=repository, retriever=FakeRetriever())

    items = await service.list_eval_sets()

    assert [item["eval_set_id"] for item in items] == ["eval_chunk"]


@pytest.mark.asyncio
async def test_service_deletes_eval_set_with_related_runs_and_results(tmp_path: Path):
    source_path = write_chunk_jsonl(tmp_path)
    repository = FakeEvalRepository()
    service = EvaluationService(repository=repository, retriever=FakeRetriever())
    generated = await service.generate(EvalSetGenerateRequest(name="smoke", total_count=1, source_path=str(source_path)))
    run = await service.start_eval_run(generated["eval_set_id"], EvalRunConfig())

    response = await service.delete_eval_set(generated["eval_set_id"])

    assert response == {
        "ok": True,
        "eval_set_id": generated["eval_set_id"],
        "deleted_eval_sets": 1,
        "deleted_cases": 1,
        "deleted_runs": 1,
        "deleted_run_results": 1,
    }
    assert await service.get_eval_set(generated["eval_set_id"]) is None
    assert await service.get_eval_run(run["run_id"]) is None
    results, total = await service.list_eval_run_results(run["run_id"])
    assert results == []
    assert total == 0


@pytest.mark.asyncio
async def test_service_starts_eval_run_with_chunk_metrics(tmp_path: Path):
    source_path = write_chunk_jsonl(tmp_path)
    repository = FakeEvalRepository()
    service = EvaluationService(repository=repository, retriever=FakeRetriever())
    generated = await service.generate(EvalSetGenerateRequest(name="smoke", total_count=1, source_path=str(source_path)))

    run = await service.start_eval_run(generated["eval_set_id"], EvalRunConfig(configured_k=5, similarity_threshold=0.72))

    assert run["ok"] is True
    assert run["summary"]["total"] == 1
    assert run["summary"]["hit_at_k"] == 1.0
    assert run["summary"]["context_recall_at_k"] == 1.0
    assert run["summary"]["mrr_at_k"] == 0.5
    assert run["summary"]["precision_at_configured_k"] == 0.2
    assert run["summary"]["precision_at_effective_k"] == 0.5
    stored = await service.get_eval_run(run["run_id"])
    assert "results" not in stored
    items, total = await service.list_eval_run_results(run["run_id"], page=1, page_size=10)
    assert total == 1
    assert items[0]["diagnostics"]["retrieved_chunk_ids"] == ["noise_chunk", "chunk_1"]
    assert items[0]["diagnostics"]["matched_chunk_ids"] == ["chunk_1"]


@pytest.mark.asyncio
async def test_service_creates_running_eval_run_before_background_completion(tmp_path: Path):
    source_path = write_chunk_jsonl(tmp_path)
    repository = FakeEvalRepository()
    service = EvaluationService(repository=repository, retriever=FakeRetriever())
    generated = await service.generate(EvalSetGenerateRequest(name="smoke", total_count=1, source_path=str(source_path)))

    created = await service.create_eval_run(generated["eval_set_id"], EvalRunConfig(configured_k=5, similarity_threshold=0.72))

    assert created["ok"] is True
    assert created["status"] == "running"
    assert created["summary"]["total"] == 1
    stored = await service.get_eval_run(created["run_id"])
    assert stored["status"] == "running"
    results, total = await service.list_eval_run_results(created["run_id"], page=1, page_size=10)
    assert results == []
    assert total == 0

    completed = await service.complete_eval_run(created["run_id"])

    assert completed["status"] == "completed"
    assert completed["summary"]["hit_at_k"] == 1.0
    stored = await service.get_eval_run(created["run_id"])
    assert stored["status"] == "completed"
    results, total = await service.list_eval_run_results(created["run_id"], page=1, page_size=10)
    assert total == 1
    assert results[0]["case_id"] == "faq_eval_000001"


@pytest.mark.asyncio
async def test_service_completes_eval_run_with_controlled_concurrency(tmp_path: Path):
    source_path = write_multi_chunk_jsonl(tmp_path, count=4)
    repository = FakeEvalRepository()
    retriever = ConcurrentTrackingRetriever()
    service = EvaluationService(repository=repository, retriever=retriever)
    generated = await service.generate(
        EvalSetGenerateRequest(
            name="smoke",
            total_count=4,
            source_path=str(source_path),
            eval_type_distribution={"single_chunk": 1.0},
            question_style_distribution={"original": 1.0},
            difficulty_distribution={"easy": 1.0},
            category_distribution={"订单相关": 1.0},
        )
    )

    created = await service.create_eval_run(generated["eval_set_id"], EvalRunConfig())
    completed = await service.complete_eval_run(created["run_id"])

    assert completed["status"] == "completed"
    assert completed["summary"]["total"] == 4
    assert retriever.max_active > 1
    results, total = await service.list_eval_run_results(created["run_id"], page=1, page_size=10)
    assert total == 4
    assert all(item["metrics"]["hit_at_k"] == 1 for item in results)


@pytest.mark.asyncio
async def test_service_updates_progress_and_result_batches_during_background_run(tmp_path: Path):
    source_path = write_multi_chunk_jsonl(tmp_path, count=6)
    repository = FakeEvalRepository()
    retriever = ConcurrentTrackingRetriever()
    service = EvaluationService(repository=repository, retriever=retriever)
    service.eval_case_concurrency = 3
    service.eval_result_commit_batch_size = 2
    generated = await service.generate(
        EvalSetGenerateRequest(
            name="progress",
            total_count=6,
            source_path=str(source_path),
            eval_type_distribution={"single_chunk": 1.0},
            question_style_distribution={"original": 1.0},
            difficulty_distribution={"easy": 1.0},
            category_distribution={"订单相关": 1.0},
        )
    )

    created = await service.create_eval_run(generated["eval_set_id"], EvalRunConfig())
    await service.complete_eval_run(created["run_id"])

    progress_updates = [patch["progress"] for patch in repository.run_updates if "progress" in patch]
    assert [item["completed_cases"] for item in progress_updates[:3]] == [2, 4, 6]
    assert progress_updates[-1]["total_cases"] == 6
    assert progress_updates[-1]["percent"] == 1.0
    assert [len(batch) for batch in repository.saved_result_batches] == [2, 2, 2]


@pytest.mark.asyncio
async def test_service_records_timing_summary(tmp_path: Path):
    source_path = write_multi_chunk_jsonl(tmp_path, count=3)
    repository = FakeEvalRepository()
    retriever = ConcurrentTrackingRetriever()
    service = EvaluationService(repository=repository, retriever=retriever)
    service.eval_case_concurrency = 2
    service.eval_result_commit_batch_size = 2
    generated = await service.generate(
        EvalSetGenerateRequest(
            name="timing",
            total_count=3,
            source_path=str(source_path),
            eval_type_distribution={"single_chunk": 1.0},
            question_style_distribution={"original": 1.0},
            difficulty_distribution={"easy": 1.0},
            category_distribution={"订单相关": 1.0},
        )
    )

    created = await service.create_eval_run(generated["eval_set_id"], EvalRunConfig())
    await service.complete_eval_run(created["run_id"])

    stored = await service.get_eval_run(created["run_id"])
    timing = stored["timing"]
    assert timing["total_ms"] >= 0
    assert timing["retrieve_ms"] >= 0
    assert timing["commit_ms"] >= 0
    assert timing["summary_ms"] >= 0
    assert timing["cases"] == 3


@pytest.mark.asyncio
async def test_service_run_overrides_apply_only_to_single_run(tmp_path: Path):
    source_path = write_multi_chunk_jsonl(tmp_path, count=4)
    repository = FakeEvalRepository()
    retriever = ConcurrentTrackingRetriever()
    service = EvaluationService(repository=repository, retriever=retriever)
    service.eval_case_concurrency = 5
    service.eval_result_commit_batch_size = 5
    generated = await service.generate(
        EvalSetGenerateRequest(
            name="override",
            total_count=4,
            source_path=str(source_path),
            eval_type_distribution={"single_chunk": 1.0},
            question_style_distribution={"original": 1.0},
            difficulty_distribution={"easy": 1.0},
            category_distribution={"订单相关": 1.0},
        )
    )

    created = await service.create_eval_run(
        generated["eval_set_id"],
        EvalRunConfig(
            configured_k=5,
            retrieval_top_n=20,
            similarity_threshold=0.72,
            rerank_enabled=True,
            case_concurrency_override=2,
            commit_batch_size_override=2,
        ),
    )
    await service.complete_eval_run(created["run_id"])

    stored = await service.get_eval_run(created["run_id"])
    assert stored["rag_config"]["case_concurrency"] == 2
    assert stored["rag_config"]["commit_batch_size"] == 2
    assert [len(batch) for batch in repository.saved_result_batches] == [2, 2]
    assert service.eval_case_concurrency == 5
    assert service.eval_result_commit_batch_size == 5


@pytest.mark.asyncio
async def test_service_rejects_eval_run_when_source_hash_changed(tmp_path: Path):
    source_path = write_chunk_jsonl(tmp_path)
    repository = FakeEvalRepository()
    service = EvaluationService(repository=repository, retriever=FakeRetriever())
    generated = await service.generate(EvalSetGenerateRequest(name="smoke", total_count=1, source_path=str(source_path)))
    source_path.write_text(source_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(EvalSourceChangedError):
        await service.start_eval_run(generated["eval_set_id"], EvalRunConfig())


@pytest.mark.asyncio
async def test_service_records_zero_effective_k_failure(tmp_path: Path):
    source_path = write_chunk_jsonl(tmp_path)
    repository = FakeEvalRepository()
    service = EvaluationService(repository=repository, retriever=EmptyRetriever())
    generated = await service.generate(EvalSetGenerateRequest(name="smoke", total_count=1, source_path=str(source_path)))

    run = await service.start_eval_run(generated["eval_set_id"], EvalRunConfig())
    items, _ = await service.list_eval_run_results(run["run_id"], page=1, page_size=10)

    assert run["summary"]["zero_context_rate"] == 1.0
    assert items[0]["metrics"]["hit_at_k"] == 0
    assert "zero_effective_k" in items[0]["diagnostics"]["failure_reasons"]
    assert "miss" in items[0]["diagnostics"]["failure_reasons"]


def write_chunk_jsonl(tmp_path: Path) -> Path:
    source_path = tmp_path / "faq.chunks.jsonl"
    row = {
        "id": "chunk_1",
        "parent_id": "FAQ_1",
        "question": "订单能修改规格吗？",
        "chunk_title": "订单能修改规格吗？",
        "chunk_text": "订单未支付可取消重拍。",
        "category_l1": "订单相关",
        "url": "https://help.jd.com/user/issue/FAQ_1.html",
        "doc_type": "faq",
        "status": "active",
        "search_enabled": True,
    }
    source_path.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    return source_path


def write_multi_chunk_jsonl(tmp_path: Path, *, count: int) -> Path:
    source_path = tmp_path / "faq-multi.chunks.jsonl"
    rows = []
    for index in range(1, count + 1):
        rows.append(
            {
                "id": f"chunk_{index}",
                "parent_id": f"FAQ_{index}",
                "question": f"问题{index}",
                "chunk_title": f"问题{index}",
                "chunk_text": f"答案{index}",
                "category_l1": "订单相关",
                "url": f"https://help.jd.com/user/issue/FAQ_{index}.html",
                "doc_type": "faq",
                "status": "active",
                "search_enabled": True,
            }
        )
    source_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    return source_path
