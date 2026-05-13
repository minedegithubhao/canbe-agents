from __future__ import annotations

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from app.evaluation.api import router, run_router
from app.evaluation.service import EvalSourceChangedError


class FakeEvaluationService:
    async def generate(self, request):
        return {"ok": True, "eval_set_id": "eval_1", "summary": {"total": request.total_count}}

    async def list_eval_sets(self, limit: int = 50, skip: int = 0):
        return [{"eval_set_id": "eval_1", "name": "smoke", "summary": {"total": 1}}]

    async def get_eval_set(self, eval_set_id: str):
        return {"eval_set_id": eval_set_id, "name": "smoke"}

    async def list_cases(self, eval_set_id: str, **kwargs):
        return ([{"case_id": "faq_eval_000001", "eval_set_id": eval_set_id, "question": "订单能修改规格吗？"}], 1)

    async def start_eval_run(self, eval_set_id: str, config):
        return {
            "ok": True,
            "run_id": "run_1",
            "eval_set_id": eval_set_id,
            "status": "completed",
            "summary": {
                "total": 1,
                "hit_at_k": 1.0,
                "context_recall_at_k": 1.0,
                "mrr_at_k": 1.0,
                "precision_at_configured_k": 0.2,
                "precision_at_effective_k": 1.0,
                "avg_effective_k": 1.0,
                "zero_context_rate": 0.0,
            },
        }

    async def create_eval_run(self, eval_set_id: str, config):
        return {
            "ok": True,
            "run_id": "run_1",
            "eval_set_id": eval_set_id,
            "status": "running",
            "summary": {
                "total": 1,
                "hit_at_k": 0.0,
                "context_recall_at_k": 0.0,
                "mrr_at_k": 0.0,
                "precision_at_configured_k": 0.0,
                "precision_at_effective_k": 0.0,
                "avg_effective_k": 0.0,
                "zero_context_rate": 0.0,
            },
        }

    async def complete_eval_run(self, run_id: str):
        return {"ok": True, "run_id": run_id, "status": "completed"}

    async def get_eval_run(self, run_id: str):
        return {"run_id": run_id, "summary": {"total": 1}, "rag_config": {}}

    async def list_eval_runs(self, eval_set_id: str, limit: int = 50, skip: int = 0):
        return [{"run_id": "run_1", "eval_set_id": eval_set_id, "summary": {"total": 1}}]

    async def list_eval_run_results(self, run_id: str, page: int = 1, page_size: int = 20, filters=None):
        return ([{"case_id": "faq_eval_000001", "metrics": {"hit_at_k": 1}, "diagnostics": {}}], 1)

    async def delete_eval_set(self, eval_set_id: str):
        return {
            "ok": True,
            "eval_set_id": eval_set_id,
            "deleted_eval_sets": 1,
            "deleted_cases": 2,
            "deleted_runs": 1,
            "deleted_run_results": 2,
        }


class SourceChangedEvaluationService(FakeEvaluationService):
    async def create_eval_run(self, eval_set_id: str, config):
        raise EvalSourceChangedError("changed")


@pytest.fixture()
def client():
    app = FastAPI()
    app.state.evaluation_service = FakeEvaluationService()
    app.include_router(router)
    app.include_router(run_router)
    return TestClient(app)


def test_generate_eval_set_api(client: TestClient):
    response = client.post("/admin/eval-sets/generate", json={"name": "smoke", "total_count": 2})

    assert response.status_code == 200
    assert response.json()["eval_set_id"] == "eval_1"
    assert response.json()["summary"]["total"] == 2


def test_list_cases_api_supports_chunk_filters(client: TestClient):
    response = client.get("/admin/eval-sets/eval_1/cases?page=1&page_size=10&category=订单相关&question_style=colloquial")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["case_id"] == "faq_eval_000001"


def test_start_eval_run_api_accepts_run_config(client: TestClient):
    response = client.post(
        "/admin/eval-sets/eval_1/runs/start",
        json={"configured_k": 5, "retrieval_top_n": 20, "similarity_threshold": 0.72, "rerank_enabled": True},
    )

    assert response.status_code == 200
    assert response.json()["run_id"] == "run_1"
    assert response.json()["status"] == "running"
    assert response.json()["summary"]["hit_at_k"] == 0.0


def test_start_eval_run_api_returns_source_changed_error():
    app = FastAPI()
    app.state.evaluation_service = SourceChangedEvaluationService()
    app.include_router(router)
    app.include_router(run_router)
    client = TestClient(app)

    response = client.post("/admin/eval-sets/eval_1/runs/start", json={})

    assert response.status_code == 409
    assert response.json()["code"] == "EVAL_SOURCE_CHANGED"


def test_get_eval_run_api_uses_eval_runs_route(client: TestClient):
    response = client.get("/admin/eval-runs/run_1")

    assert response.status_code == 200
    assert response.json()["run_id"] == "run_1"


def test_list_eval_runs_api_returns_runs_for_eval_set(client: TestClient):
    response = client.get("/admin/eval-sets/eval_1/runs")

    assert response.status_code == 200
    assert response.json()["items"][0]["run_id"] == "run_1"


def test_list_eval_run_results_api_returns_paginated_results(client: TestClient):
    response = client.get("/admin/eval-runs/run_1/results?page=1&page_size=10")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["metrics"]["hit_at_k"] == 1


def test_delete_eval_set_api_returns_delete_summary(client: TestClient):
    response = client.delete("/admin/eval-sets/eval_1")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["deleted_cases"] == 2
    assert response.json()["deleted_run_results"] == 2
