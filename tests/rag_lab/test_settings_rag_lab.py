from pathlib import Path

from app.settings import get_settings
from app.settings_rag_lab import (
    RAG_LAB_ARTIFACT_ROOT,
    RAG_LAB_MYSQL_URL,
    RAG_LAB_WORKER_ENABLED,
)
import pytest


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_rag_lab_defaults_are_exposed():
    settings = get_settings()

    assert settings.mysql_url == RAG_LAB_MYSQL_URL
    assert isinstance(settings.artifact_root, Path)
    assert settings.artifact_root == RAG_LAB_ARTIFACT_ROOT
    assert settings.worker_enabled == RAG_LAB_WORKER_ENABLED


def test_rag_lab_env_overrides_are_exposed(monkeypatch):
    monkeypatch.setenv("MYSQL_URL", "mysql+pymysql://tester:secret@localhost:3306/override_db")
    monkeypatch.setenv("ARTIFACT_ROOT", "tmp/rag-lab-artifacts")
    monkeypatch.setenv("WORKER_ENABLED", "false")

    settings = get_settings()

    assert settings.mysql_url == "mysql+pymysql://tester:secret@localhost:3306/override_db"
    assert isinstance(settings.artifact_root, Path)
    assert settings.artifact_root == Path("tmp/rag-lab-artifacts")
    assert settings.worker_enabled is False
