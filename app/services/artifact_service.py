from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable


class ArtifactService:
    def __init__(
        self,
        artifact_root: Path | str,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.artifact_root = Path(artifact_root)
        self._now_provider = now_provider or datetime.now

    def write_json(self, artifact_type: str, payload: dict[str, Any]) -> dict[str, str]:
        target_dir = self._artifact_dir(artifact_type)
        target_dir.mkdir(parents=True, exist_ok=True)

        canonical_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = sha256(canonical_payload.encode("utf-8")).hexdigest()
        storage_path = target_dir / f"{digest}.json"
        storage_path.write_text(canonical_payload, encoding="utf-8")

        return {
            "artifact_type": artifact_type,
            "storage_path": str(storage_path),
        }

    def read_json(self, storage_path: Path | str) -> dict[str, Any]:
        path = Path(storage_path)
        return json.loads(path.read_text(encoding="utf-8"))

    def _artifact_dir(self, artifact_type: str) -> Path:
        date_path = self._now_provider().strftime("%Y/%m/%d")
        return self.artifact_root / date_path / artifact_type
