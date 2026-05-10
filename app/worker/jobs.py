from __future__ import annotations

from typing import Any


class InlineExperimentQueueDispatcher:
    def dispatch_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload


async def run_experiment_job(
    experiment_service: Any,
    *,
    experiment_run_id: int,
    eval_set_id: int,
    pipeline_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await experiment_service.execute_run(
        experiment_run_id=experiment_run_id,
        eval_set_id=eval_set_id,
        pipeline_snapshot=pipeline_snapshot,
    )
