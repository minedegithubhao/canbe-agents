from __future__ import annotations

import pytest

from app.evaluation.repository import EvalSetRepository


class FakeIndexCollection:
    def __init__(self) -> None:
        self.indexes: list[tuple] = []

    async def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))


class FakeDb(dict):
    def __getitem__(self, name: str):
        if name not in self:
            self[name] = FakeIndexCollection()
        return dict.__getitem__(self, name)


class FakeMongo:
    def __init__(self) -> None:
        self.db = FakeDb()

    def available(self) -> bool:
        return True

    def collection(self, suffix: str) -> str:
        return f"test_{suffix}"


@pytest.mark.asyncio
async def test_repository_ensures_chunk_eval_indexes():
    mongo = FakeMongo()
    repository = EvalSetRepository(mongo)

    await repository.ensure_indexes()

    eval_sets = mongo.db["test_eval_sets"].indexes
    eval_cases = mongo.db["test_eval_cases"].indexes
    eval_runs = mongo.db["test_eval_runs"].indexes
    eval_run_results = mongo.db["test_eval_run_results"].indexes
    assert ([("created_at", -1)], {}) in eval_sets
    assert ([("eval_set_id", 1), ("case_id", 1)], {"unique": True}) in eval_cases
    assert ([("eval_set_id", 1), ("category", 1)], {}) in eval_cases
    assert ([("eval_set_id", 1), ("eval_type", 1)], {}) in eval_cases
    assert ([("eval_set_id", 1), ("difficulty", 1)], {}) in eval_cases
    assert ([("eval_set_id", 1), ("question_style", 1)], {}) in eval_cases
    assert ([("eval_set_id", 1), ("created_at", -1)], {}) in eval_runs
    assert ([("run_id", 1), ("case_id", 1)], {"unique": True}) in eval_run_results
    assert ([("run_id", 1), ("metrics.hit_at_k", 1)], {}) in eval_run_results
    assert ([("run_id", 1), ("metrics.context_recall_at_k", 1)], {}) in eval_run_results
    assert ([("run_id", 1), ("diagnostics.effective_k", 1)], {}) in eval_run_results
