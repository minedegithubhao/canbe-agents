from __future__ import annotations

from typing import Any

from app.services.metrics_service import MetricsService


class JudgementService:
    def __init__(
        self,
        *,
        answer_correctness_pass_threshold: float = 0.8,
        metrics_service: MetricsService | None = None,
    ) -> None:
        self.answer_correctness_pass_threshold = answer_correctness_pass_threshold
        self.metrics_service = metrics_service or MetricsService()

    def discrete_verdict(
        self,
        *,
        answer_correctness: float,
        source_valid: bool,
        overreach: bool,
        fallback_correct: bool,
    ) -> dict[str, Any]:
        passed = (
            answer_correctness >= self.answer_correctness_pass_threshold
            and source_valid
            and not overreach
            and fallback_correct
        )
        failed_checks: list[str] = []
        if answer_correctness < self.answer_correctness_pass_threshold:
            failed_checks.append("answer_correctness")
        if not source_valid:
            failed_checks.append("source_valid")
        if overreach:
            failed_checks.append("overreach")
        if not fallback_correct:
            failed_checks.append("fallback_correct")

        return {
            "pass": passed,
            "answer_correctness": float(answer_correctness),
            "source_valid": source_valid,
            "overreach": overreach,
            "fallback_correct": fallback_correct,
            "thresholds": {
                "answer_correctness_pass_threshold": self.answer_correctness_pass_threshold,
            },
            "failed_checks": failed_checks,
            "metrics": [
                self.metrics_service.metric_result(
                    metric_name="answer_correctness",
                    score=answer_correctness,
                    passed=answer_correctness
                    >= self.answer_correctness_pass_threshold,
                    reason=None
                    if answer_correctness
                    >= self.answer_correctness_pass_threshold
                    else "below_threshold",
                ).model_dump(),
                self.metrics_service.metric_result(
                    metric_name="source_valid",
                    passed=source_valid,
                    reason=None if source_valid else "invalid_source",
                ).model_dump(),
                self.metrics_service.metric_result(
                    metric_name="overreach",
                    passed=not overreach,
                    reason=None if not overreach else "overreach_detected",
                ).model_dump(),
                self.metrics_service.metric_result(
                    metric_name="fallback_correct",
                    passed=fallback_correct,
                    reason=None if fallback_correct else "fallback_incorrect",
                ).model_dump(),
            ],
        }
