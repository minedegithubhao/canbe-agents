from pathlib import Path

from scripts.bootstrap_rag_lab_from_existing_assets import discover_assets


def test_bootstrap_discovers_existing_jsonl_assets():
    assets = discover_assets(Path("exports"))

    assert "cleaned_jsonl" in assets
