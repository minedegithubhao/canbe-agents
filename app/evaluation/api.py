from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.evaluation.schemas import EvalSetGenerateRequest

router = APIRouter(prefix="/admin/eval-sets", tags=["evaluation"])


@router.post("/generate")
async def generate_eval_set(request: Request, payload: EvalSetGenerateRequest) -> dict:
    return await request.app.state.evaluation_service.generate(payload)


@router.get("")
async def list_eval_sets(request: Request, limit: int = Query(50, ge=1, le=200), skip: int = Query(0, ge=0)) -> dict:
    return {"items": await request.app.state.evaluation_service.list_eval_sets(limit=limit, skip=skip)}


@router.get("/{eval_set_id}")
async def get_eval_set(request: Request, eval_set_id: str) -> dict:
    item = await request.app.state.evaluation_service.get_eval_set(eval_set_id)
    return {"ok": item is not None, "item": item}


@router.get("/{eval_set_id}/cases")
async def list_cases(
    request: Request,
    eval_set_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    validation_status: str | None = None,
    category_l1: str | None = None,
    eval_type: str | None = None,
    difficulty: str | None = None,
) -> dict:
    items, total = await request.app.state.evaluation_service.list_cases(
        eval_set_id,
        page=page,
        page_size=page_size,
        validation_status=validation_status,
        category_l1=category_l1,
        eval_type=eval_type,
        difficulty=difficulty,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{eval_set_id}/export")
async def export_eval_set(request: Request, eval_set_id: str) -> dict:
    return {"items": await request.app.state.evaluation_service.export_for_evaluate_retrieval(eval_set_id)}


@router.post("/{eval_set_id}/check-stale")
async def check_stale_cases(request: Request, eval_set_id: str) -> dict:
    return await request.app.state.evaluation_service.check_stale_cases(eval_set_id)


@router.post("/{eval_set_id}/runs/start")
async def start_eval_run(request: Request, eval_set_id: str) -> dict:
    return await request.app.state.evaluation_service.start_eval_run(eval_set_id, request.app.state.chat_service)


@router.get("/{eval_set_id}/runs")
async def list_eval_runs(request: Request, eval_set_id: str, limit: int = Query(50, ge=1, le=200), skip: int = Query(0, ge=0)) -> dict:
    return {"items": await request.app.state.evaluation_service.list_eval_runs(eval_set_id, limit=limit, skip=skip)}


@router.get("/runs/{run_id}")
async def get_eval_run(request: Request, run_id: str) -> dict:
    item = await request.app.state.evaluation_service.get_eval_run(run_id)
    return item or {"ok": False, "run_id": run_id}


@router.get("/runs/{run_id}/results")
async def list_eval_run_results(
    request: Request,
    run_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> dict:
    items, total = await request.app.state.evaluation_service.list_eval_run_results(run_id, page=page, page_size=page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}
