from __future__ import annotations

from collections.abc import Iterable, Sequence
from statistics import mean
from typing import Any

from pydantic import BaseModel, Field


class MetricResult(BaseModel):
    metric_name: str
    score: float | None = None
    passed: bool | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagasMetricAdapter:
    def __init__(self, metric_name: str) -> None:
        self.metric_name = metric_name

    def evaluate_case(self, case_result: dict[str, Any]) -> MetricResult:
        score = _coerce_optional_float(case_result.get(self.metric_name))
        return MetricResult(
            metric_name=self.metric_name,
            score=score,
            metadata={
                "adapter": "ragas_placeholder",
                "implemented": False,
            },
        )


class MetricsService:
    def __init__(self) -> None:
        self._ragas_adapters = {
            metric_name: RagasMetricAdapter(metric_name)
            for metric_name in (
                "answer_correctness",
                "faithfulness",
                "source_grounding",
            )
        }

    def metric_result(
        self,
        *,
        metric_name: str,
        score: float | None = None,
        passed: bool | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MetricResult:
        return MetricResult(
            metric_name=metric_name,
            score=score,
            passed=passed,
            reason=reason,
            metadata=metadata or {},
        )

    def evaluate_with_ragas_placeholder(
        self, case_result: dict[str, Any]
    ) -> list[MetricResult]:
        return [
            adapter.evaluate_case(case_result)
            for adapter in self._ragas_adapters.values()
        ]

    def aggregate_run(
        self, case_results: Sequence[dict[str, Any]] | Iterable[dict[str, Any]]
    ) -> dict[str, Any]:
        items = list(case_results)
        answer_correctness_scores = _collect_optional_floats(
            items, "answer_correctness"
        )
        faithfulness_scores = _collect_optional_floats(items, "faithfulness")
        source_grounding_scores = _collect_optional_floats(items, "source_grounding")

        pass_count = sum(1 for item in items if bool(item.get("pass")))
        fallback_count = sum(
            1 for item in items if _coerce_fallback_correct(item) is True
        )
        overreach_count = sum(1 for item in items if bool(item.get("overreach")))
        source_valid_count = sum(1 for item in items if bool(item.get("source_valid")))

        total_cases = len(items)
        return {
            "case_count": total_cases,
            "pass_count": pass_count,
            "pass_rate": _rate(pass_count, total_cases),
            "fallback_count": fallback_count,
            "fallback_rate": _rate(fallback_count, total_cases),
            "overreach_count": overreach_count,
            "overreach_rate": _rate(overreach_count, total_cases),
            "source_valid_rate": _rate(source_valid_count, total_cases),
            "answer_correctness_avg": _average(answer_correctness_scores),
            "faithfulness_avg": _average(faithfulness_scores),
            "source_grounding_avg": _average(source_grounding_scores),
        }


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _collect_optional_floats(
    items: Sequence[dict[str, Any]], key: str
) -> list[float]:
    values: list[float] = []
    for item in items:
        value = item.get(key)
        if value is None:
            continue
        values.append(float(value))
    return values


def _average(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return float(mean(values))


def _coerce_fallback_correct(item: dict[str, Any]) -> bool | None:
    has_fallback_correct = "fallback_correct" in item
    has_legacy_fallback = "fallback" in item

    if has_fallback_correct and has_legacy_fallback:
        fallback_correct = bool(item.get("fallback_correct"))
        legacy_fallback = bool(item.get("fallback"))
        if fallback_correct != legacy_fallback:
            raise ValueError(
                "Conflicting fallback fields: 'fallback_correct' and legacy "
                "'fallback' disagree."
            )
        return fallback_correct

    if has_fallback_correct:
        return bool(item.get("fallback_correct"))

    if has_legacy_fallback:
        return bool(item.get("fallback"))

    return None


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return count / total
