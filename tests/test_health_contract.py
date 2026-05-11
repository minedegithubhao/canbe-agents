import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conftest import get_json
from app.api.health import _normalize_status


def test_health_contract(require_api, api_base_url: str) -> None:
    response = get_json(api_base_url, "/health")

    assert isinstance(response, dict)
    assert response.get("status") in {"ok", "degraded", "error"}

    dependencies = response.get("dependencies")
    if dependencies is not None:
        assert isinstance(dependencies, dict)
        for name, status in dependencies.items():
            assert isinstance(name, str)
            assert status in {"ok", "degraded", "error", "unconfigured"}


def test_bailian_configured_status_is_healthy() -> None:
    assert _normalize_status("bailian_configured") == "ok"
