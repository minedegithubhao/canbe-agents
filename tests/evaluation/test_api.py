from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.evaluation.api import router


class FakeEvaluationService:
    async def generate(self, request):
        return {"ok": True, "eval_set_id": "eval_1", "summary": {"total": request.total_count, "validated": request.total_count}}

    async def list_eval_sets(self, limit: int = 50, skip: int = 0):
        return [{"eval_set_id": "eval_1", "name": "smoke", "summary": {"total": 1}}]

    async def get_eval_set(self, eval_set_id: str):
        return {"eval_set_id": eval_set_id, "name": "smoke"}

    async def list_cases(self, eval_set_id: str, **kwargs):
        return ([{"case_id": "faq_eval_000001", "eval_set_id": eval_set_id, "question": "订单能修改规格吗？"}], 1)

    async def export_for_evaluate_retrieval(self, eval_set_id: str):
        return [{"id": "faq_eval_000001", "query": "订单能修改规格吗？", "caseType": "单FAQ语义等价", "expectedFallback": False}]

    async def check_stale_cases(self, eval_set_id: str):
        return {"summary": {"total": 1, "valid": 1, "stale": 0}, "items": [{"case_id": "faq_eval_000001", "status": "valid", "reason": ""}]}

    async def start_eval_run(self, eval_set_id: str, chat_service):
        return {"ok": True, "run_id": "run_1", "eval_set_id": eval_set_id, "summary": {"total": 1, "passed": 1}}

    async def get_eval_run(self, run_id: str):
        return {"run_id": run_id, "summary": {"total": 1, "passed": 1}, "results": []}

    async def list_eval_runs(self, eval_set_id: str, limit: int = 50, skip: int = 0):
        return [{"run_id": "run_1", "eval_set_id": eval_set_id, "summary": {"total": 1, "passed": 1}}]

    async def list_eval_run_results(self, run_id: str, page: int = 1, page_size: int = 20):
        return ([{"case_id": "faq_eval_000001", "ok": False, "failure_reasons": ["missing sources"]}], 1)


@pytest.fixture()
def client():
    app = FastAPI()
    app.state.evaluation_service = FakeEvaluationService()
    app.include_router(router)
    return TestClient(app)


def test_generate_eval_set_api(client: TestClient):
    response = client.post("/admin/eval-sets/generate", json={"name": "smoke", "total_count": 2})

    assert response.status_code == 200
    assert response.json()["eval_set_id"] == "eval_1"
    assert response.json()["summary"]["validated"] == 2


def test_list_cases_api_supports_pagination(client: TestClient):
    response = client.get("/admin/eval-sets/eval_1/cases?page=1&page_size=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["case_id"] == "faq_eval_000001"


def test_export_api_returns_evaluate_retrieval_format(client: TestClient):
    response = client.get("/admin/eval-sets/eval_1/export")

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "faq_eval_000001"


def test_stale_check_api_returns_summary(client: TestClient):
    response = client.post("/admin/eval-sets/eval_1/check-stale")

    assert response.status_code == 200
    assert response.json()["summary"]["valid"] == 1


def test_start_eval_run_api_returns_run_summary(client: TestClient):
    client.app.state.chat_service = object()

    response = client.post("/admin/eval-sets/eval_1/runs/start")

    assert response.status_code == 200
    assert response.json()["run_id"] == "run_1"
    assert response.json()["summary"]["passed"] == 1


def test_get_eval_run_api_returns_run(client: TestClient):
    response = client.get("/admin/eval-sets/runs/run_1")

    assert response.status_code == 200
    assert response.json()["run_id"] == "run_1"


def test_list_eval_runs_api_returns_runs_for_eval_set(client: TestClient):
    response = client.get("/admin/eval-sets/eval_1/runs")

    assert response.status_code == 200
    assert response.json()["items"][0]["run_id"] == "run_1"


def test_list_eval_run_results_api_returns_paginated_results(client: TestClient):
    response = client.get("/admin/eval-sets/runs/run_1/results?page=1&page_size=10")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["failure_reasons"] == ["missing sources"]
