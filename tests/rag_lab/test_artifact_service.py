from datetime import datetime
from hashlib import sha256
from pathlib import Path

from app.services.artifact_service import ArtifactService


def test_artifact_service_writes_trace_to_date_and_type_path(tmp_path: Path):
    fixed_now = datetime(2026, 5, 10, 8, 30, 0)
    service = ArtifactService(tmp_path, now_provider=lambda: fixed_now)
    payload = {"ok": True}

    artifact = service.write_json("trace", payload)

    expected_digest = sha256(b'{"ok":true}').hexdigest()
    expected_path = tmp_path / "2026" / "05" / "10" / "trace" / f"{expected_digest}.json"

    assert artifact["artifact_type"] == "trace"
    assert Path(artifact["storage_path"]) == expected_path
    assert expected_path.exists()


def test_artifact_service_writes_report_to_date_and_type_path(tmp_path: Path):
    fixed_now = datetime(2026, 5, 10, 8, 30, 0)
    service = ArtifactService(tmp_path, now_provider=lambda: fixed_now)
    payload = {"summary": "done", "score": 0.8}

    artifact = service.write_json("report", payload)

    expected_digest = sha256(b'{"score":0.8,"summary":"done"}').hexdigest()
    expected_path = tmp_path / "2026" / "05" / "10" / "report" / f"{expected_digest}.json"

    assert artifact["artifact_type"] == "report"
    assert Path(artifact["storage_path"]) == expected_path
    assert expected_path.exists()


def test_artifact_service_read_json_round_trip(tmp_path: Path):
    fixed_now = datetime(2026, 5, 10, 8, 30, 0)
    service = ArtifactService(tmp_path, now_provider=lambda: fixed_now)
    payload = {"items": [1, 2, 3], "nested": {"flag": True}, "title": "中文"}

    artifact = service.write_json("trace", payload)

    assert service.read_json(artifact["storage_path"]) == payload
