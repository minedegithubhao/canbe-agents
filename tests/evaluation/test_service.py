from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.schemas import EvalSetGenerateRequest
from app.evaluation.service import EvaluationService
from app.schemas.chat import ChatResponse, SourceRef


class FakeEvalRepository:
    def __init__(self) -> None:
        self.eval_sets: dict[str, dict] = {}
        self.eval_cases: list[dict] = []
        self.stale_updates: list[dict] = []
        self.eval_runs: dict[str, dict] = {}

    async def save_generated_eval_set(self, generated):
        self.eval_sets[generated.eval_set_id] = {
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

    async def get_current_answers(self, faq_ids: list[str]):
        return {faq_id: "未支付可取消重拍。" for faq_id in faq_ids}


    async def update_stale_check_results(self, eval_set_id: str, results):
        for result in results:
            self.stale_updates.append(
                {
                    "eval_set_id": eval_set_id,
                    "case_id": result.case_id,
                    "stale_status": result.status,
                    "stale_reason": result.reason,
                }
            )

    async def save_eval_run(self, run):
        self.eval_runs[run["run_id"]] = run

    async def get_eval_run(self, run_id: str):
        return self.eval_runs.get(run_id)

    async def list_eval_runs(self, eval_set_id: str, limit: int = 50, skip: int = 0):
        rows = [run for run in self.eval_runs.values() if run["eval_set_id"] == eval_set_id]
        return rows[skip : skip + limit]

    async def list_eval_run_results(self, run_id: str, page: int = 1, page_size: int = 20):
        run = self.eval_runs.get(run_id) or {}
        results = list(run.get("results") or [])
        start = (page - 1) * page_size
        return results[start : start + page_size], len(results)


class FakeChatService:
    async def chat(self, query: str, session_id: str | None = None, top_k: int | None = None, candidate_id: str | None = None):
        return ChatResponse(
            answer="ok",
            confidence=0.95,
            sources=[
                SourceRef(
                    id="FAQ_001",
                    title=query,
                    category="FAQ",
                    source="JD Help FAQ",
                    sourceUrl="https://help.jd.com/user/issue/292-553.html",
                    score=0.95,
                )
            ],
            suggestedQuestions=[],
            fallback=False,
            traceId="trace_1",
        )


class FailingChatService:
    async def chat(self, query: str, session_id: str | None = None, top_k: int | None = None, candidate_id: str | None = None):
        return ChatResponse(
            answer="no source",
            confidence=0.2,
            sources=[],
            suggestedQuestions=[],
            fallback=True,
            traceId="trace_fail",
        )


@pytest.mark.asyncio
async def test_service_generates_and_saves_eval_set(tmp_path: Path):
    source_path = write_cleaned_jsonl(tmp_path)
    service = EvaluationService(repository=FakeEvalRepository())

    response = await service.generate(EvalSetGenerateRequest(name="smoke", total_count=1, seed=11, source_path=str(source_path)))

    assert response["ok"] is True
    assert response["eval_set_id"] == "eval_11"
    assert response["summary"]["validated"] == 1
    stored_cases, total = await service.list_cases(response["eval_set_id"])
    assert total == 1
    assert stored_cases[0]["case_id"] == "faq_eval_000001"


@pytest.mark.asyncio
async def test_service_uses_eval_set_scoped_case_storage_ids(tmp_path: Path):
    source_path = write_cleaned_jsonl(tmp_path)
    repository = FakeEvalRepository()
    service = EvaluationService(repository=repository)

    first = await service.generate(EvalSetGenerateRequest(name="first", total_count=1, seed=21, source_path=str(source_path)))
    second = await service.generate(EvalSetGenerateRequest(name="second", total_count=1, seed=22, source_path=str(source_path)))

    assert first["eval_set_id"] != second["eval_set_id"]
    assert {case["_id"] for case in repository.eval_cases} == {
        "eval_21:faq_eval_000001",
        "eval_22:faq_eval_000001",
    }


@pytest.mark.asyncio
async def test_service_exports_validated_cases_for_evaluate_retrieval(tmp_path: Path):
    source_path = write_cleaned_jsonl(tmp_path)
    service = EvaluationService(repository=FakeEvalRepository())
    response = await service.generate(EvalSetGenerateRequest(name="smoke", total_count=1, seed=12, source_path=str(source_path)))

    exported = await service.export_for_evaluate_retrieval(response["eval_set_id"])

    assert exported == [
        {
            "id": "faq_eval_000001",
            "query": "订单能修改规格吗？",
            "caseType": "single_faq_equivalent",
            "expectedFallback": False,
            "expectedSourceDomain": "help.jd.com",
        }
    ]


@pytest.mark.asyncio
async def test_service_checks_stale_cases_against_current_answers(tmp_path: Path):
    source_path = write_cleaned_jsonl(tmp_path)
    service = EvaluationService(repository=FakeEvalRepository())
    response = await service.generate(EvalSetGenerateRequest(name="smoke", total_count=1, seed=13, source_path=str(source_path)))

    stale_report = await service.check_stale_cases(response["eval_set_id"])

    assert stale_report["summary"] == {"total": 1, "valid": 1, "stale": 0}
    assert stale_report["items"][0]["status"] == "valid"


@pytest.mark.asyncio
async def test_service_persists_stale_check_results(tmp_path: Path):
    source_path = write_cleaned_jsonl(tmp_path)
    repository = FakeEvalRepository()
    service = EvaluationService(repository=repository)
    response = await service.generate(EvalSetGenerateRequest(name="smoke", total_count=1, seed=14, source_path=str(source_path)))

    await service.check_stale_cases(response["eval_set_id"])

    assert repository.stale_updates == [
        {
            "eval_set_id": "eval_14",
            "case_id": "faq_eval_000001",
            "stale_status": "valid",
            "stale_reason": "",
        }
    ]


@pytest.mark.asyncio
async def test_service_starts_eval_run_and_persists_summary(tmp_path: Path):
    source_path = write_cleaned_jsonl(tmp_path)
    repository = FakeEvalRepository()
    service = EvaluationService(repository=repository)
    generated = await service.generate(EvalSetGenerateRequest(name="smoke", total_count=1, seed=15, source_path=str(source_path)))

    run = await service.start_eval_run(generated["eval_set_id"], chat_service=FakeChatService())

    assert run["ok"] is True
    assert run["eval_set_id"] == "eval_15"
    assert run["summary"] == {
        "total": 1,
        "passed": 1,
        "passRate": 1.0,
        "answerableHitRate": 1.0,
        "fallbackRate": 0.0,
        "sourceCompletenessRate": 1.0,
        "overreachViolations": 0,
    }
    stored = await service.get_eval_run(run["run_id"])
    assert stored["results"][0]["case_id"] == "faq_eval_000001"
    assert stored["results"][0]["ok"] is True


@pytest.mark.asyncio
async def test_service_lists_eval_runs_for_eval_set(tmp_path: Path):
    source_path = write_cleaned_jsonl(tmp_path)
    repository = FakeEvalRepository()
    service = EvaluationService(repository=repository)
    generated = await service.generate(EvalSetGenerateRequest(name="smoke", total_count=1, seed=16, source_path=str(source_path)))
    first = await service.start_eval_run(generated["eval_set_id"], chat_service=FakeChatService())
    second = await service.start_eval_run(generated["eval_set_id"], chat_service=FakeChatService())

    runs = await service.list_eval_runs(generated["eval_set_id"])

    assert [run["run_id"] for run in runs] == [first["run_id"], second["run_id"]]


@pytest.mark.asyncio
async def test_service_lists_eval_run_results_with_failure_reasons(tmp_path: Path):
    source_path = write_cleaned_jsonl(tmp_path)
    repository = FakeEvalRepository()
    service = EvaluationService(repository=repository)
    generated = await service.generate(EvalSetGenerateRequest(name="smoke", total_count=1, seed=17, source_path=str(source_path)))
    run = await service.start_eval_run(generated["eval_set_id"], chat_service=FailingChatService())

    items, total = await service.list_eval_run_results(run["run_id"], page=1, page_size=10)

    assert total == 1
    assert items[0]["ok"] is False
    assert "fallback mismatch" in items[0]["failure_reasons"]
    assert "missing sources" in items[0]["failure_reasons"]


def write_cleaned_jsonl(tmp_path: Path) -> Path:
    source_path = tmp_path / "cleaned.jsonl"
    row = {
        "id": "FAQ_001",
        "question": "订单能修改规格吗？",
        "answer_clean": "未支付可取消重拍。",
        "category_l1": "订单相关",
        "category_l2": "订单修改",
        "category_l3": "规格修改",
        "url": "https://help.jd.com/user/issue/292-553.html",
        "doc_type": "faq",
        "status": "active",
        "search_enabled": True,
    }
    source_path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    return source_path
