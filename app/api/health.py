from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    state = request.app.state
    dependencies = {
        "mongodb": getattr(state.mongo, "status", "not_initialized"),
        "milvus": getattr(state.milvus, "status", "not_initialized"),
        "elasticsearch": getattr(state.es, "status", "not_initialized"),
        "redis": getattr(state.redis, "status", "not_initialized"),
        "embedder": getattr(state.embedder, "status", "not_loaded"),
        "reranker": getattr(state.reranker, "status", "not_loaded"),
        "deepseek": "configured" if state.deepseek.configured() else "not_configured",
    }
    normalized = {name: _normalize_status(value) for name, value in dependencies.items()}
    status = "ok" if any(value == "ok" for value in normalized.values()) else "degraded"
    return HealthResponse(status=status, dependencies=normalized)


def _normalize_status(value: str) -> str:
    if value == "ok":
        return "ok"
    if value in {"not_initialized", "not_loaded", "not_configured", "unconfigured"}:
        return "unconfigured"
    if value == "configured":
        return "ok"
    if value.startswith("unavailable") or value.startswith("fallback") or value in {"disabled", "unreachable"}:
        return "degraded"
    return "degraded"
