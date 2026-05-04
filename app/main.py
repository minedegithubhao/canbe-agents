from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import chat, faq, health, ingest
from app.chat import ChatService
from app.db import ElasticSearch, Milvus, Mongo, RedisStore
from app.ingest import IngestService
from app.llm import DeepSeek
from app.retrieval import Embedder, Reranker, Retriever
from app.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
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

    app.state.retriever = Retriever(app.state.mongo, app.state.milvus, app.state.es, app.state.embedder, app.state.reranker)
    app.state.ingest_service = IngestService(app.state.mongo, app.state.milvus, app.state.es, app.state.redis, app.state.embedder)
    app.state.chat_service = ChatService(app.state.mongo, app.state.retriever, app.state.deepseek)
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
    return app


app = create_app()
