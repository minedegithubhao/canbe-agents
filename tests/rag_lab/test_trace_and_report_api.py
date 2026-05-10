from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from app.main import app


class _TraceExperimentService:
    def get_run_summary(self, run_id: int):
        return {
            "id": run_id,
            "status": "completed",
            "summary_json": {"pass_rate": 1.0},
        }

    def get_case_trace(self, run_id: int, case_id: int):
        return {
            "experiment_run_id": run_id,
            "eval_case_id": case_id,
            "trace": {"sections": ["input", "retrieval", "verdict"]},
        }


class _TraceComparisonService:
    def get_comparison_summary(self, comparison_id: int):
        return {
            "id": comparison_id,
            "verdict": "beneficial",
        }

    def get_report_download(self, comparison_id: int):
        return {
            "comparison_id": comparison_id,
            "artifact_type": "comparison_report",
            "file_name": f"comparison-{comparison_id}.json",
        }


@asynccontextmanager
async def _test_lifespan(test_app):
    test_app.state.rag_lab_experiment_service = _TraceExperimentService()
    test_app.state.rag_lab_comparison_service = _TraceComparisonService()
    yield


def test_run_trace_endpoint_exists():
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan

    with TestClient(app) as client:
        response = client.get("/rag-lab/runs/1/cases/1/trace")

    app.router.lifespan_context = original_lifespan
    assert response.status_code != 404


def test_run_summary_endpoint_returns_service_payload():
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan

    with TestClient(app) as client:
        response = client.get("/rag-lab/runs/1")

    app.router.lifespan_context = original_lifespan
    assert response.status_code == 200
    assert response.json() == {
        "item": {
            "id": 1,
            "status": "completed",
            "summary_json": {"pass_rate": 1.0},
        }
    }


def test_case_trace_endpoint_returns_service_payload():
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan

    with TestClient(app) as client:
        response = client.get("/rag-lab/runs/1/cases/1/trace")

    app.router.lifespan_context = original_lifespan
    assert response.status_code == 200
    assert response.json() == {
        "item": {
            "experiment_run_id": 1,
            "eval_case_id": 1,
            "trace": {"sections": ["input", "retrieval", "verdict"]},
        }
    }


def test_comparison_summary_endpoint_returns_service_payload():
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan

    with TestClient(app) as client:
        response = client.get("/rag-lab/comparisons/2")

    app.router.lifespan_context = original_lifespan
    assert response.status_code == 200
    assert response.json() == {
        "item": {
            "id": 2,
            "verdict": "beneficial",
        }
    }


def test_comparison_report_download_endpoint_returns_metadata():
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan

    with TestClient(app) as client:
        response = client.get("/rag-lab/comparisons/2/report")

    app.router.lifespan_context = original_lifespan
    assert response.status_code == 200
    assert response.json() == {
        "item": {
            "comparison_id": 2,
            "artifact_type": "comparison_report",
            "file_name": "comparison-2.json",
        }
    }
