from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import chat, faq, health, ingest
from app.evaluation import api as evaluation_api
from app.evaluation.repository import EvalSetRepository
from app.evaluation.service import EvaluationService
from app.repositories.storage import ElasticSearch, Milvus, Mongo, RedisStore
from app.services.chat_service import ChatService
from app.services.ingest_service import IngestService
from app.services.llm_service import DeepSeek
from app.services.retrieval_service import Embedder, Reranker, Retriever
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

    await app.state.mongo.connect()
    await app.state.redis.connect()
    await app.state.es.connect()
    await app.state.milvus.connect()

    # 依赖装配顺序反映了核心调用链：
    # 用户问题 -> Retriever 检索证据 -> ChatService 调用 LLM 生成回答。
    app.state.retriever = Retriever(app.state.mongo, app.state.milvus, app.state.es, app.state.embedder, app.state.reranker)
    app.state.ingest_service = IngestService(app.state.mongo, app.state.milvus, app.state.es, app.state.redis, app.state.embedder)
    app.state.chat_service = ChatService(app.state.mongo, app.state.retriever, app.state.deepseek)
    app.state.eval_repository = EvalSetRepository(app.state.mongo)
    await app.state.eval_repository.ensure_indexes()
    app.state.evaluation_service = EvaluationService(app.state.eval_repository)
    try:
        yield
    finally:
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
    app.include_router(evaluation_api.router)
    return app


app = create_app()
