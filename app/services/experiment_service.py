from __future__ import annotations

from typing import Any

from app.services.judgement_service import JudgementService


class ExperimentService:
    def __init__(
        self,
        run_repository: Any,
        eval_repository: Any,
        runtime: Any,
        metrics_service: Any,
        queue_dispatcher: Any,
        *,
        judgement_service: JudgementService | None = None,
    ) -> None:
        self.run_repository = run_repository
        self.eval_repository = eval_repository
        self.runtime = runtime
        self.metrics_service = metrics_service
        self.queue_dispatcher = queue_dispatcher
        self.judgement_service = judgement_service or JudgementService()

    def new_run_payload(
        self,
        *,
        dataset_version_id: int,
        pipeline_version_id: int,
        eval_set_id: int,
        triggered_by: str | None = None,
    ) -> dict[str, Any]:
        return {
            "dataset_version_id": self._require_positive_int(
                "dataset_version_id", dataset_version_id
            ),
            "pipeline_version_id": self._require_positive_int(
                "pipeline_version_id", pipeline_version_id
            ),
            "eval_set_id": self._require_positive_int("eval_set_id", eval_set_id),
            "triggered_by": self._normalize_triggered_by(triggered_by),
            "run_no": 1,
            "status": "draft",
        }

    def create_run(
        self,
        *,
        dataset_version_id: int,
        pipeline_version_id: int,
        eval_set_id: int,
        triggered_by: str | None = None,
    ) -> dict[str, Any]:
        repository = self._require_dependency("run_repository", self.run_repository)
        payload = self.new_run_payload(
            dataset_version_id=dataset_version_id,
            pipeline_version_id=pipeline_version_id,
            eval_set_id=eval_set_id,
            triggered_by=triggered_by,
        )
        run = repository.create_run(**payload)
        queued_run = repository.update_status(run.id, "queued")
        dispatcher = self._require_dependency("queue_dispatcher", self.queue_dispatcher)
        dispatcher.dispatch_run(
            {
                "job": "experiment_run",
                "experiment_run_id": queued_run.id,
                "eval_set_id": queued_run.eval_set_id,
            }
        )
        return self._serialize_run(queued_run)

    def list_runs(self) -> list[dict[str, Any]]:
        repository = self._require_dependency("run_repository", self.run_repository)
        list_method = getattr(repository, "list_runs", None)
        if list_method is None:
            raise ValueError("run_repository must implement list_runs()")
        return [self._serialize_run(item) for item in list_method()]

    def get_run_summary(self, run_id: int) -> dict[str, Any]:
        repository = self._require_dependency("run_repository", self.run_repository)
        get_method = getattr(repository, "get_run_summary", None)
        if get_method is None:
            raise ValueError("run_repository must implement get_run_summary()")
        return self._serialize_run(get_method(run_id))

    def get_case_trace(self, run_id: int, case_id: int) -> dict[str, Any]:
        repository = self._require_dependency("run_repository", self.run_repository)
        get_method = getattr(repository, "get_case_trace", None)
        if get_method is None:
            raise ValueError("run_repository must implement get_case_trace()")
        result = get_method(run_id, case_id)
        if isinstance(result, dict):
            return result
        return {
            "experiment_run_id": getattr(result, "experiment_run_id", None),
            "eval_case_id": getattr(result, "eval_case_id", None),
            "trace_artifact_id": getattr(result, "trace_artifact_id", None),
            "judgement_json": getattr(result, "judgement_json", None),
        }

    async def execute_run(
        self,
        *,
        experiment_run_id: int,
        eval_set_id: int,
        pipeline_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = self._require_positive_int("experiment_run_id", experiment_run_id)
        eval_set_id = self._require_positive_int("eval_set_id", eval_set_id)
        repository = self._require_dependency("run_repository", self.run_repository)
        eval_repository = self._require_dependency("eval_repository", self.eval_repository)
        runtime = self._require_dependency("runtime", self.runtime)
        metrics_service = self._require_dependency("metrics_service", self.metrics_service)

        repository.update_status(run_id, "running")
        case_results_for_summary: list[dict[str, Any]] = []

        for eval_case in eval_repository.list_cases(eval_set_id):
            runtime_result = await runtime.run(
                getattr(eval_case, "query"),
                pipeline_snapshot=pipeline_snapshot,
            )
            case_evaluation = self._evaluate_case(eval_case, runtime_result)
            verdict = self.judgement_service.discrete_verdict(
                answer_correctness=case_evaluation["answer_correctness"],
                source_valid=case_evaluation["source_valid"],
                overreach=case_evaluation["overreach"],
                fallback_correct=case_evaluation["fallback_correct_for_verdict"],
            )

            repository.save_case_result(
                experiment_run_id=run_id,
                eval_case_id=getattr(eval_case, "id"),
                status="completed",
                fallback=bool(getattr(runtime_result, "fallback", False)),
                answer=getattr(runtime_result, "answer", None),
                confidence=self._optional_float(getattr(runtime_result, "confidence", None)),
                retrieval_score=self._extract_score(runtime_result, "retrieval_score"),
                rerank_score=self._extract_score(runtime_result, "rerank_score"),
                judgement_json=verdict,
                trace_artifact_id=None,
            )
            case_results_for_summary.append(
                {
                    "pass": bool(verdict["pass"]),
                    "fallback_correct": case_evaluation["fallback_observed"],
                }
            )

        summary = metrics_service.aggregate_run(case_results_for_summary)
        repository.save_summary(run_id, summary)
        repository.update_status(run_id, "completed")
        return {
            "experiment_run_id": run_id,
            "status": "completed",
            "summary": summary,
        }

    def _evaluate_case(self, eval_case: Any, runtime_result: Any) -> dict[str, Any]:
        behavior = getattr(eval_case, "behavior_json", {}) or {}
        should_answer = bool(behavior.get("should_answer", True))
        fallback_observed = bool(getattr(runtime_result, "fallback", False))
        answer = (getattr(runtime_result, "answer", "") or "").strip()
        expected_answer = (getattr(eval_case, "expected_answer", "") or "").strip()

        if should_answer:
            answer_correctness = 1.0 if answer and answer == expected_answer else 0.0
            overreach = fallback_observed
            fallback_correct_for_verdict = not fallback_observed
        else:
            answer_correctness = 1.0 if fallback_observed else 0.0
            overreach = not fallback_observed
            fallback_correct_for_verdict = fallback_observed

        return {
            "answer_correctness": answer_correctness,
            "source_valid": True,
            "overreach": overreach,
            "fallback_correct_for_verdict": fallback_correct_for_verdict,
            "fallback_observed": fallback_observed,
        }

    def _extract_score(self, runtime_result: Any, score_name: str) -> float | None:
        debug = getattr(runtime_result, "debug", {}) or {}
        direct = debug.get(score_name)
        if direct is not None:
            return self._optional_float(direct)
        top_hit_scores = debug.get("top_hit_scores") or []
        if top_hit_scores:
            return self._optional_float(top_hit_scores[0])
        return None

    def _serialize_run(self, run: Any) -> dict[str, Any]:
        return {
            "id": getattr(run, "id", None),
            "dataset_version_id": getattr(run, "dataset_version_id", None),
            "pipeline_version_id": getattr(run, "pipeline_version_id", None),
            "eval_set_id": getattr(run, "eval_set_id", None),
            "run_no": getattr(run, "run_no", None),
            "status": getattr(run, "status", None),
            "triggered_by": getattr(run, "triggered_by", None),
            "summary_json": getattr(run, "summary_json", {}),
        }

    def _normalize_triggered_by(self, triggered_by: str | None) -> str | None:
        if triggered_by is None:
            return None
        normalized = triggered_by.strip()
        return normalized or None

    def _require_positive_int(self, field_name: str, value: int) -> int:
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f"{field_name} must be a positive integer")
        return value

    def _require_dependency(self, dependency_name: str, dependency: Any) -> Any:
        if dependency is None:
            raise ValueError(f"{dependency_name} is required")
        return dependency

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        return float(value)
