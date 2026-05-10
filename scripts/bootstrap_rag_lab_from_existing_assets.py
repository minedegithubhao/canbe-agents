from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_first_row(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        first_line = handle.readline().strip()
    return json.loads(first_line) if first_line else {}


def _count_jsonl_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def discover_assets(exports_dir: Path) -> dict[str, Any]:
    cleaned_candidates = sorted(exports_dir.glob("*.cleaned.jsonl"))
    chunk_candidates = sorted(exports_dir.glob("*.chunks.jsonl"))

    assets: dict[str, Any] = {
        "exports_dir": str(exports_dir),
        "cleaned_jsonl": [str(path) for path in cleaned_candidates],
        "chunk_jsonl": [str(path) for path in chunk_candidates],
    }

    if cleaned_candidates:
        cleaned_path = cleaned_candidates[0]
        assets["cleaned_summary"] = {
            "path": str(cleaned_path),
            "row_count": _count_jsonl_rows(cleaned_path),
            "sample_id": _read_first_row(cleaned_path).get("id"),
        }

    if chunk_candidates:
        chunk_path = chunk_candidates[0]
        assets["chunk_summary"] = {
            "path": str(chunk_path),
            "row_count": _count_jsonl_rows(chunk_path),
            "sample_id": _read_first_row(chunk_path).get("id"),
        }

    return assets


def build_dataset_manifest(assets: dict[str, Any]) -> dict[str, Any]:
    cleaned_summary = assets.get("cleaned_summary", {})
    chunk_summary = assets.get("chunk_summary", {})

    return {
        "dataset_name": "bootstrap-from-existing-faq-assets",
        "source_type": "jsonl",
        "cleaned_jsonl": cleaned_summary.get("path"),
        "chunk_jsonl": chunk_summary.get("path"),
        "document_count": cleaned_summary.get("row_count", 0),
        "chunk_count": chunk_summary.get("row_count", 0),
        "bootstrap_mode": "existing_assets",
    }


def build_eval_manifest(assets: dict[str, Any]) -> dict[str, Any]:
    cleaned_summary = assets.get("cleaned_summary", {})

    return {
        "eval_set_name": "starter-eval-from-existing-faq-assets",
        "source_dataset": cleaned_summary.get("path"),
        "seed_document_count": cleaned_summary.get("row_count", 0),
        "generation_strategy": "question_as_query",
        "bootstrap_mode": "existing_assets",
    }


def write_starter_manifests(assets: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_manifest_path = output_dir / "starter_dataset_manifest.json"
    eval_manifest_path = output_dir / "starter_eval_set_manifest.json"

    dataset_manifest_path.write_text(
        json.dumps(build_dataset_manifest(assets), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    eval_manifest_path.write_text(
        json.dumps(build_eval_manifest(assets), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "dataset_manifest": str(dataset_manifest_path),
        "eval_set_manifest": str(eval_manifest_path),
    }


def format_migration_summary(assets: dict[str, Any], manifest_paths: dict[str, str]) -> str:
    cleaned_summary = assets.get("cleaned_summary", {})
    chunk_summary = assets.get("chunk_summary", {})

    lines = [
        "RAG Lab bootstrap summary",
        f"- exports_dir: {assets['exports_dir']}",
        f"- cleaned_jsonl_files: {len(assets['cleaned_jsonl'])}",
        f"- chunk_jsonl_files: {len(assets['chunk_jsonl'])}",
        f"- cleaned_rows: {cleaned_summary.get('row_count', 0)}",
        f"- chunk_rows: {chunk_summary.get('row_count', 0)}",
        f"- dataset_manifest: {manifest_paths['dataset_manifest']}",
        f"- eval_set_manifest: {manifest_paths['eval_set_manifest']}",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap RAG Lab manifests from existing FAQ export assets.",
    )
    parser.add_argument(
        "--exports-dir",
        default="exports",
        help="Directory containing cleaned and chunk JSONL assets.",
    )
    parser.add_argument(
        "--output-dir",
        default="exports/rag_lab_bootstrap",
        help="Directory where starter manifests will be written.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    assets = discover_assets(Path(args.exports_dir))
    manifest_paths = write_starter_manifests(assets, Path(args.output_dir))
    print(format_migration_summary(assets, manifest_paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
