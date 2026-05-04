from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas import IngestResponse, IngestTaskResponse

router = APIRouter(prefix="/admin/ingest", tags=["ingest"])


@router.post("/import", response_model=IngestResponse)
async def import_knowledge(request: Request) -> IngestResponse:
    try:
        counts, status = await request.app.state.ingest_service.import_cleaned_knowledge()
        return IngestResponse(ok=True, message="import completed", counts=counts, status=status)
    except Exception as exc:
        return IngestResponse(ok=False, message=f"import failed: {type(exc).__name__}: {exc}")


@router.post("/build-index", response_model=IngestTaskResponse)
async def build_index(request: Request) -> IngestTaskResponse:
    try:
        task = await request.app.state.ingest_service.start_build_index_task()
        return IngestTaskResponse(ok=True, message="build-index accepted", task=task)
    except Exception as exc:
        return IngestTaskResponse(ok=False, message=f"build-index failed: {type(exc).__name__}: {exc}")


@router.get("/tasks/{task_id}", response_model=IngestTaskResponse)
async def get_task(request: Request, task_id: str) -> IngestTaskResponse:
    task = await request.app.state.ingest_service.get_task(task_id)
    if not task:
        return IngestTaskResponse(ok=False, message="task not found")
    return IngestTaskResponse(ok=True, message="task found", task=task)
