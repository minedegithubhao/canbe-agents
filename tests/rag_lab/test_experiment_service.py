import pytest

from app.services.experiment_service import ExperimentService


class StubRun:
    def __init__(
        self,
        *,
        run_id: int = 41,
        dataset_version_id: int,
        pipeline_version_id: int,
        eval_set_id: int,
        run_no: int = 1,
        status: str = "draft",
        triggered_by: str | None = None,
        summary_json: dict | None = None,
    ) -> None:
        self.id = run_id
        self.dataset_version_id = dataset_version_id
        self.pipeline_version_id = pipeline_version_id
        self.eval_set_id = eval_set_id
        self.run_no = run_no
        self.status = status
        self.triggered_by = triggered_by
        self.summary_json = summary_json or {}


class StubRunRepository:
    def __init__(self) -> None:
        self.created_runs: list[StubRun] = []
        self.status_updates: list[tuple[int, str]] = []
        self.case_results: list[dict] = []
        self.saved_summaries: list[tuple[int, dict]] = []

    def create_run(
        self,
        *,
        dataset_version_id: int,
        pipeline_version_id: int,
        eval_set_id: int,
        run_no: int,
        status: str = "draft",
        triggered_by: str | None = None,
    ) -> StubRun:
        run = StubRun(
            dataset_version_id=dataset_version_id,
            pipeline_version_id=pipeline_version_id,
            eval_set_id=eval_set_id,
            run_no=run_no,
            status=status,
            triggered_by=triggered_by,
        )
        self.created_runs.append(run)
        return run

    def update_status(self, experiment_run_id: int, status: str) -> StubRun:
        self.status_updates.append((experiment_run_id, status))
        run = self.created_runs[-1]
        run.status = status
        return run

    def save_case_result(self, **kwargs) -> dict:
        self.case_results.append(kwargs)
        return kwargs

    def save_summary(self, experiment_run_id: int, summary_json: dict) -> StubRun:
        self.saved_summaries.append((experiment_run_id, summary_json))
        run = self.created_runs[-1]
        run.summary_json = summary_json
        return run


class StubEvalRepository:
    def list_cases(self, eval_set_id: int) -> list[object]:
        return [
            type(
                "EvalCase",
                (),
                {
                    "id": 101,
                    "query": "reset password",
                    "expected_answer": "use reset flow",
                    "behavior_json": {"should_answer": True},
                },
            )(),
            type(
                "EvalCase",
                (),
                {
                    "id": 102,
                    "query": "track order",
                    "expected_answer": "not answerable",
                    "behavior_json": {"should_answer": False},
                },
            )(),
        ]


class StubQueueDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def dispatch_run(self, payload: dict) -> dict:
        self.calls.append(payload)
        return payload


class StubRuntime:
    async def run(self, query: str, pipeline_snapshot: dict | None = None, top_k: int | None = None):
        if query == "reset password":
            return type(
                "RuntimeResult",
                (),
                {
                    "answer": "use reset flow",
                    "confidence": 0.93,
                    "fallback": False,
                    "trace": {"verdict": {"fallback": False}},
                    "debug": {"top_hit_scores": [0.91]},
                },
            )()

        return type(
            "RuntimeResult",
            (),
            {
                "answer": "No highly relevant public FAQ was found for this question.",
                "confidence": 0.12,
                "fallback": True,
                "trace": {"verdict": {"fallback": True}},
                "debug": {"top_hit_scores": [0.12]},
            },
        )()


class StubJudgementService:
    def discrete_verdict(
        self,
        *,
        answer_correctness: float,
        source_valid: bool,
        overreach: bool,
        fallback_correct: bool,
    ) -> dict:
        return {
            "pass": answer_correctness >= 0.8 and source_valid and not overreach and fallback_correct,
            "answer_correctness": answer_correctness,
            "source_valid": source_valid,
            "overreach": overreach,
            "fallback_correct": fallback_correct,
        }


class StubMetricsService:
    def aggregate_run(self, case_results: list[dict]) -> dict:
        return {
            "case_count": len(case_results),
            "pass_count": sum(1 for item in case_results if item["pass"]),
            "pass_rate": sum(1 for item in case_results if item["pass"]) / len(case_results),
            "fallback_count": sum(1 for item in case_results if item["fallback_correct"]),
            "fallback_rate": sum(1 for item in case_results if item["fallback_correct"]) / len(case_results),
        }


def test_experiment_service_creates_run_in_draft_state():
    service = ExperimentService(None, None, None, None, None)

    run = service.new_run_payload(
        dataset_version_id=11,
        pipeline_version_id=22,
        eval_set_id=33,
        triggered_by="  tester  ",
    )

    assert run == {
        "dataset_version_id": 11,
        "pipeline_version_id": 22,
        "eval_set_id": 33,
        "triggered_by": "tester",
        "run_no": 1,
        "status": "draft",
    }


def test_experiment_service_rejects_non_positive_run_inputs():
    service = ExperimentService(None, None, None, None, None)

    with pytest.raises(ValueError, match="dataset_version_id must be a positive integer"):
        service.new_run_payload(
            dataset_version_id=0,
            pipeline_version_id=1,
            eval_set_id=1,
            triggered_by="tester",
        )


def test_experiment_service_creates_run_and_dispatches_queue_job():
    run_repository = StubRunRepository()
    queue_dispatcher = StubQueueDispatcher()
    service = ExperimentService(
        run_repository,
        None,
        None,
        None,
        queue_dispatcher,
    )

    run = service.create_run(
        dataset_version_id=7,
        pipeline_version_id=8,
        eval_set_id=9,
        triggered_by="tester",
    )

    assert run["id"] == 41
    assert queue_dispatcher.calls == [
        {
            "job": "experiment_run",
            "experiment_run_id": 41,
            "eval_set_id": 9,
        }
    ]
    assert run_repository.created_runs[0].status == "queued"


@pytest.mark.asyncio
async def test_experiment_service_executes_cases_updates_status_and_persists_summary():
    run_repository = StubRunRepository()
    queue_dispatcher = StubQueueDispatcher()
    runtime = StubRuntime()
    metrics_service = StubMetricsService()
    judgement_service = StubJudgementService()
    eval_repository = StubEvalRepository()
    service = ExperimentService(
        run_repository,
        eval_repository,
        runtime,
        metrics_service,
        queue_dispatcher,
        judgement_service=judgement_service,
    )

    created_run = service.create_run(
        dataset_version_id=1,
        pipeline_version_id=2,
        eval_set_id=3,
        triggered_by="tester",
    )

    summary = await service.execute_run(
        experiment_run_id=created_run["id"],
        eval_set_id=created_run["eval_set_id"],
        pipeline_snapshot={"version": "baseline-v1"},
    )

    assert run_repository.status_updates == [
        (created_run["id"], "queued"),
        (created_run["id"], "running"),
        (created_run["id"], "completed"),
    ]
    assert [item["eval_case_id"] for item in run_repository.case_results] == [101, 102]
    assert run_repository.saved_summaries == [
        (
            created_run["id"],
            {
                "case_count": 2,
                "pass_count": 2,
                "pass_rate": 1.0,
                "fallback_count": 1,
                "fallback_rate": 0.5,
            },
        )
    ]
    assert summary["status"] == "completed"
    assert summary["summary"]["pass_rate"] == 1.0
