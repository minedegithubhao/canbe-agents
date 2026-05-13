from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.evaluation.schemas import EvalRunConfig, EvalSetGenerateRequest
from app.evaluation.service import EvalSourceChangedError

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


@router.delete("/{eval_set_id}")
async def delete_eval_set(request: Request, eval_set_id: str) -> dict:
    return await request.app.state.evaluation_service.delete_eval_set(eval_set_id)


@router.get("/{eval_set_id}/cases")
async def list_cases(
    request: Request,
    eval_set_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    category: str | None = None,
    eval_type: str | None = None,
    difficulty: str | None = None,
    question_style: str | None = None,
) -> dict:
    items, total = await request.app.state.evaluation_service.list_cases(
        eval_set_id,
        page=page,
        page_size=page_size,
        category=category,
        eval_type=eval_type,
        difficulty=difficulty,
        question_style=question_style,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/{eval_set_id}/runs/start")
async def start_eval_run(request: Request, eval_set_id: str, payload: EvalRunConfig | None = None) -> dict:
    try:
        created = await request.app.state.evaluation_service.create_eval_run(eval_set_id, payload or EvalRunConfig())
        asyncio.create_task(request.app.state.evaluation_service.complete_eval_run(created["run_id"]))
        return created
    except EvalSourceChangedError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "code": "EVAL_SOURCE_CHANGED",
                "message": "评估集数据源已变化，请重新生成评估集后再运行评估。",
            },
        )


@router.get("/{eval_set_id}/runs")
async def list_eval_runs(request: Request, eval_set_id: str, limit: int = Query(50, ge=1, le=200), skip: int = Query(0, ge=0)) -> dict:
    return {"items": await request.app.state.evaluation_service.list_eval_runs(eval_set_id, limit=limit, skip=skip)}


run_router = APIRouter(prefix="/admin/eval-runs", tags=["evaluation"])


@run_router.get("/{run_id}")
async def get_eval_run(request: Request, run_id: str) -> dict:
    item = await request.app.state.evaluation_service.get_eval_run(run_id)
    return item or {"ok": False, "run_id": run_id}


@run_router.get("/{run_id}/results")
async def list_eval_run_results(
    request: Request,
    run_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> dict:
    items, total = await request.app.state.evaluation_service.list_eval_run_results(run_id, page=page, page_size=page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}
