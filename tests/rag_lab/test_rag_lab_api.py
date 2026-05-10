from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from app.main import app
from app.services.comparison_service import ComparisonService
from app.services.dataset_service import DatasetService
from app.services.eval_service import EvalService
from app.services.experiment_service import ExperimentService
from app.services.pipeline_service import PipelineService


@asynccontextmanager
async def _test_lifespan(test_app):
    test_app.state.rag_lab_dataset_service = DatasetService(None, None, object())
    test_app.state.rag_lab_pipeline_service = PipelineService(None)
    test_app.state.rag_lab_eval_service = EvalService(None)
    test_app.state.rag_lab_experiment_service = ExperimentService(
        None, None, None, None, None
    )
    test_app.state.rag_lab_comparison_service = ComparisonService()
    yield


def test_rag_lab_dataset_router_is_registered():
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan

    with TestClient(app) as client:
        response = client.get("/rag-lab/datasets")

    app.router.lifespan_context = original_lifespan
    assert response.status_code != 404


def test_incompletely_wired_pipeline_route_returns_service_error():
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan

    with TestClient(app) as client:
        response = client.post(
            "/rag-lab/pipelines/1/versions",
            json={
                "version_no": 1,
                "payload": {
                    "chunking_config": {"strategy": "fixed"},
                    "retrieval_config": {"dense_enabled": True},
                    "recall_config": {"fusion_strategy": "rrf"},
                    "rerank_config": {"rerank_enabled": False},
                    "prompt_config": {"system_prompt_template": "answer"},
                    "fallback_config": {"medium_confidence_threshold": 0.5},
                },
            },
        )

    app.router.lifespan_context = original_lifespan
    assert response.status_code in {501, 503}


def test_create_dataset_route_awaits_async_service_result():
    class AsyncDatasetService:
        async def create_dataset(self, **kwargs):
            return {
                "id": 7,
                "code": kwargs["code"],
                "name": kwargs["name"],
            }

        def list_datasets(self):
            return []

    @asynccontextmanager
    async def _async_dataset_lifespan(test_app):
        test_app.state.rag_lab_dataset_service = AsyncDatasetService()
        test_app.state.rag_lab_pipeline_service = PipelineService(None)
        test_app.state.rag_lab_eval_service = EvalService(None)
        test_app.state.rag_lab_experiment_service = ExperimentService(
            None, None, None, None, None
        )
        test_app.state.rag_lab_comparison_service = ComparisonService()
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _async_dataset_lifespan

    with TestClient(app) as client:
        response = client.post(
            "/rag-lab/datasets",
            json={"code": "faq", "name": "FAQ"},
        )

    app.router.lifespan_context = original_lifespan
    assert response.status_code == 200
    assert response.json() == {
        "item": {
            "id": 7,
            "code": "faq",
            "name": "FAQ",
        }
    }
