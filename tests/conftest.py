import os
import socket
import urllib.error
import urllib.request
from typing import Any

import pytest


DEFAULT_BASE_URL = "http://127.0.0.1:8801"
ALLOWED_SOURCE_URL = "https://help.jd.com/user/issue.html"
ALLOWED_SOURCE_URL_PREFIX = "https://help.jd.com/user/issue/"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--api-base-url",
        action="store",
        default=os.getenv("FAQ_RAG_API_BASE_URL", DEFAULT_BASE_URL),
        help="FAQ RAG API base URL, for example http://127.0.0.1:8801",
    )


@pytest.fixture(scope="session")
def api_base_url(pytestconfig: pytest.Config) -> str:
    return str(pytestconfig.getoption("--api-base-url")).rstrip("/")


@pytest.fixture(scope="session")
def api_available(api_base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{api_base_url}/health", timeout=2) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, socket.timeout):
        return False


@pytest.fixture()
def require_api(api_available: bool) -> None:
    if not api_available:
        pytest.skip("FAQ RAG API is not available. Set FAQ_RAG_API_BASE_URL or start FastAPI first.")


def post_json(api_base_url: str, path: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{api_base_url}{path}",
        data=__import__("json").dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return __import__("json").loads(body)


def get_json(api_base_url: str, path: str, timeout: int = 10) -> dict[str, Any] | list[Any]:
    with urllib.request.urlopen(f"{api_base_url}{path}", timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return __import__("json").loads(body)
