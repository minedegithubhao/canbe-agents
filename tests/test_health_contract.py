from conftest import get_json


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
