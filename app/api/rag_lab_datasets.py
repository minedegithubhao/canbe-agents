from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/rag-lab/datasets", tags=["rag-lab"])


@router.get("")
async def list_datasets(request: Request) -> dict[str, list[Any]]:
    list_method = _require_service_method(
        request,
        "rag_lab_dataset_service",
        "list_datasets",
        "Dataset listing",
    )
    items = await _invoke_service_method(list_method)
    return {"items": [_serialize_item(item) for item in items]}


@router.post("")
async def create_dataset(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    create_method = _require_service_method(
        request,
        "rag_lab_dataset_service",
        "create_dataset",
        "Dataset creation",
    )
    result = await _invoke_service_method(create_method, **payload)
    return {"item": _serialize_item(result)}


@router.post("/{dataset_id}/versions")
async def create_dataset_version(
    dataset_id: int,
    payload: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    create_method = _require_service_method(
        request,
        "rag_lab_dataset_service",
        "ingest_version",
        "Dataset version creation",
    )
    result = await _invoke_service_method(
        create_method,
        dataset_id=dataset_id,
        **payload,
    )
    return {"item": _serialize_item(result)}


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


async def _invoke_service_method(method: Any, **kwargs: Any) -> Any:
    try:
        result = method(**kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result
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
