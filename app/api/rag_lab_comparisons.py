from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/rag-lab/comparisons", tags=["rag-lab"])


@router.get("")
async def list_comparisons(request: Request) -> dict[str, list[Any]]:
    list_method = _require_service_method(
        request,
        "rag_lab_comparison_service",
        "list_comparisons",
        "Comparison listing",
    )
    items = _invoke_service_method(list_method)
    return {"items": [_serialize_item(item) for item in items]}


@router.get("/{comparison_id}")
async def get_comparison_summary(
    comparison_id: int,
    request: Request,
) -> dict[str, Any]:
    get_method = _require_service_method(
        request,
        "rag_lab_comparison_service",
        "get_comparison_summary",
        "Comparison summary retrieval",
    )
    item = _invoke_service_method(get_method, comparison_id=comparison_id)
    return {"item": _serialize_item(item)}


@router.post("")
async def create_comparison(
    payload: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    compare_method = _require_service_method(
        request,
        "rag_lab_comparison_service",
        "compare_runs",
        "Comparison creation",
    )
    result = _invoke_service_method(compare_method, **payload)
    return {"item": _serialize_item(result)}


@router.get("/{comparison_id}/report")
async def get_comparison_report_download(
    comparison_id: int,
    request: Request,
) -> dict[str, Any]:
    get_method = _require_service_method(
        request,
        "rag_lab_comparison_service",
        "get_report_download",
        "Comparison report download metadata retrieval",
    )
    item = _invoke_service_method(get_method, comparison_id=comparison_id)
    return {"item": _serialize_item(item)}


def _require_service(request: Request, service_name: str) -> Any:
    service = getattr(request.app.state, service_name, None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{service_name} is not configured.",
        )
    return service


def _require_service_method(
    request: Request,
    service_name: str,
    method_name: str,
    capability_name: str,
) -> Any:
    service = _require_service(request, service_name)
    method = getattr(service, method_name, None)
    if method is None or not callable(method):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"{capability_name} is not implemented by the service layer.",
        )
    return method


def _invoke_service_method(method: Any, **kwargs: Any) -> Any:
    try:
        return method(**kwargs)
    except AttributeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service dependencies are not fully configured.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def _serialize_item(item: Any) -> Any:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "__dict__"):
        return {
            key: value
            for key, value in vars(item).items()
            if not key.startswith("_")
        }
    return item
