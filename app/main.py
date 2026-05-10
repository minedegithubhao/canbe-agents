from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import (
    chat,
    faq,
    health,
    ingest,
    rag_lab_comparisons,
    rag_lab_datasets,
    rag_lab_eval_sets,
    rag_lab_pipelines,
    rag_lab_runs,
)
from app.repositories.mysql.dataset_repository import DatasetRepository
from app.repositories.mysql.eval_repository import EvalRepository
from app.repositories.mysql.pipeline_repository import PipelineRepository
from app.repositories.mysql.run_repository import RunRepository
from app.repositories.mysql.session import get_session_factory
from app.repositories.storage import ElasticSearch, Milvus, Mongo, RedisStore
from app.services.artifact_service import ArtifactService
from app.services.chat_service import ChatService
from app.services.comparison_service import ComparisonService
from app.services.dataset_service import DatasetService
from app.services.eval_service import EvalService
from app.services.experiment_service import ExperimentService
from app.services.ingest_service import IngestService
from app.services.metrics_service import MetricsService
from app.services.llm_service import DeepSeek
from app.services.pipeline_service import PipelineService
from app.services.retrieval_service import Embedder, Reranker, Retriever
from app.worker.jobs import InlineExperimentQueueDispatcher
from app.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期入口：集中创建外部依赖，并把服务对象挂到 app.state。

    FastAPI 的路由函数本身保持很薄；真正的业务状态都在这里装配。
    这样做的好处是：依赖只初始化一次，请求处理时直接复用连接和服务对象。
    """
    app.state.settings = get_settings()
    app.state.mongo = Mongo()
    app.state.redis = RedisStore()
    app.state.es = ElasticSearch()
    app.state.milvus = Milvus()
    app.state.embedder = Embedder()
    app.state.reranker = Reranker()
    app.state.deepseek = DeepSeek()
    app.state.mysql_session_factory = get_session_factory()

    await app.state.mongo.connect()
    await app.state.redis.connect()
    await app.state.es.connect()
    await app.state.milvus.connect()

    # 依赖装配顺序反映了核心调用链：
    # 用户问题 -> Retriever 检索证据 -> ChatService 调用 LLM 生成回答。
    app.state.retriever = Retriever(app.state.mongo, app.state.milvus, app.state.es, app.state.embedder, app.state.reranker)
    app.state.ingest_service = IngestService(app.state.mongo, app.state.milvus, app.state.es, app.state.redis, app.state.embedder)
    app.state.chat_service = ChatService(app.state.mongo, app.state.retriever, app.state.deepseek)
    mysql_session = app.state.mysql_session_factory()
    app.state.rag_lab_mysql_session = mysql_session
    dataset_repository = DatasetRepository(mysql_session)
    dataset_version_repository = dataset_repository
    pipeline_repository = PipelineRepository(mysql_session)
    eval_repository = EvalRepository(mysql_session)
    run_repository = RunRepository(mysql_session)
    artifact_service = ArtifactService("artifacts")

    app.state.rag_lab_artifact_service = artifact_service
    app.state.rag_lab_dataset_service = DatasetService(dataset_repository, dataset_version_repository, app.state.ingest_service)
    app.state.rag_lab_pipeline_service = PipelineService(pipeline_repository)
    app.state.rag_lab_eval_service = EvalService(eval_repository)
    app.state.rag_lab_experiment_service = ExperimentService(
        run_repository,
        eval_repository,
        app.state.chat_service.runtime,
        MetricsService(),
        InlineExperimentQueueDispatcher(),
    )
    app.state.rag_lab_comparison_service = ComparisonService()
    try:
        yield
    finally:
        mysql_session.close()
        await app.state.mongo.close()
        await app.state.redis.close()
        await app.state.es.close()
        await app.state.milvus.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(faq.router)
    app.include_router(ingest.router)
    app.include_router(rag_lab_datasets.router)
    app.include_router(rag_lab_pipelines.router)
    app.include_router(rag_lab_eval_sets.router)
    app.include_router(rag_lab_runs.router)
    app.include_router(rag_lab_comparisons.router)
    return app


app = create_app()
