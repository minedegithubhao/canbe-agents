from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from numbers import Real
from typing import Any


class ComparisonService:
    """Compare two experiment runs and produce an operator-facing verdict."""

    QUALITY_METRIC_ALIASES = {
        "pass_rate": "pass_rate",
        "answer_correctness": "answer_correctness_avg",
        "faithfulness": "faithfulness_avg",
        "source_grounding": "source_grounding_avg",
        "fallback_rate": "fallback_rate",
        "source_valid_rate": "source_valid_rate",
        "overreach_rate": "overreach_rate",
    }

    def __init__(
        self,
        *,
        beneficial_quality_delta: float = 0.01,
        harmful_quality_delta: float = -0.02,
        harmful_risk_delta: float = 0.02,
        high_risk_answer_delta: float = -0.20,
    ) -> None:
        self.beneficial_quality_delta = beneficial_quality_delta
        self.harmful_quality_delta = harmful_quality_delta
        self.harmful_risk_delta = harmful_risk_delta
        self.high_risk_answer_delta = high_risk_answer_delta

    def compare_runs(
        self,
        *,
        baseline_summary: Mapping[str, Any],
        candidate_summary: Mapping[str, Any],
        baseline_cases: Sequence[Mapping[str, Any]] | Iterable[Mapping[str, Any]],
        candidate_cases: Sequence[Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        metric_diffs = self.aggregate_metric_diffs(
            baseline_summary=baseline_summary,
            candidate_summary=candidate_summary,
        )
        bucket_analysis = self.analyze_case_buckets(
            baseline_cases=baseline_cases,
            candidate_cases=candidate_cases,
        )
        verdict = self.verdict(
            delta_answer_correctness=metric_diffs["delta_answer_correctness"],
            delta_pass_rate=metric_diffs["delta_pass_rate"],
            delta_faithfulness=metric_diffs["delta_faithfulness"],
            delta_overreach_rate=metric_diffs["delta_overreach_rate"],
            high_risk_regression_count=bucket_analysis["high_risk_regression_count"],
        )
        return {
            "metric_diffs": metric_diffs,
            "bucket_analysis": bucket_analysis,
            "verdict": verdict,
            "recommendation": self.recommendation(
                verdict=verdict,
                metric_diffs=metric_diffs,
                bucket_analysis=bucket_analysis,
            ),
        }

    def list_comparisons(self) -> list[dict[str, Any]]:
        return []

    def get_comparison_summary(self, comparison_id: int) -> dict[str, Any]:
        raise ValueError("comparison summary retrieval is not wired yet")

    def get_report_download(self, comparison_id: int) -> dict[str, Any]:
        raise ValueError("comparison report retrieval is not wired yet")

    def aggregate_metric_diffs(
        self,
        *,
        baseline_summary: Mapping[str, Any],
        candidate_summary: Mapping[str, Any],
    ) -> dict[str, float]:
        return {
            "delta_pass_rate": self._delta(
                baseline_summary, candidate_summary, "pass_rate"
            ),
            "delta_answer_correctness": self._delta(
                baseline_summary, candidate_summary, "answer_correctness_avg"
            ),
            "delta_faithfulness": self._delta(
                baseline_summary, candidate_summary, "faithfulness_avg"
            ),
            "delta_source_grounding": self._delta(
                baseline_summary, candidate_summary, "source_grounding_avg"
            ),
            "delta_fallback_rate": self._delta(
                baseline_summary, candidate_summary, "fallback_rate"
            ),
            "delta_source_valid_rate": self._delta(
                baseline_summary, candidate_summary, "source_valid_rate"
            ),
            "delta_overreach_rate": self._delta(
                baseline_summary, candidate_summary, "overreach_rate"
            ),
        }

    def analyze_case_buckets(
        self,
        *,
        baseline_cases: Sequence[Mapping[str, Any]] | Iterable[Mapping[str, Any]],
        candidate_cases: Sequence[Mapping[str, Any]] | Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        baseline_by_id = self._index_cases(baseline_cases)
        candidate_by_id = self._index_cases(candidate_cases)

        improved_cases: list[dict[str, Any]] = []
        regressed_cases: list[dict[str, Any]] = []
        unchanged_cases: list[dict[str, Any]] = []
        high_risk_regressions: list[dict[str, Any]] = []

        shared_case_ids = sorted(set(baseline_by_id) & set(candidate_by_id))
        for case_id in shared_case_ids:
            baseline_case = baseline_by_id[case_id]
            candidate_case = candidate_by_id[case_id]
            comparison = self._compare_case_pair(
                case_id=case_id,
                baseline_case=baseline_case,
                candidate_case=candidate_case,
            )

            if comparison["status"] == "improved":
                improved_cases.append(comparison)
                continue
            if comparison["status"] == "regressed":
                regressed_cases.append(comparison)
                if comparison["high_risk"]:
                    high_risk_regressions.append(comparison)
                continue
            unchanged_cases.append(comparison)

        return {
            "baseline_only_case_count": len(set(baseline_by_id) - set(candidate_by_id)),
            "candidate_only_case_count": len(set(candidate_by_id) - set(baseline_by_id)),
            "shared_case_count": len(shared_case_ids),
            "improved_case_count": len(improved_cases),
            "regressed_case_count": len(regressed_cases),
            "unchanged_case_count": len(unchanged_cases),
            "high_risk_regression_count": len(high_risk_regressions),
            "improved_cases": improved_cases,
            "regressed_cases": regressed_cases,
            "high_risk_regressions": high_risk_regressions,
        }

    def verdict(
        self,
        *,
        delta_answer_correctness: float,
        delta_pass_rate: float,
        delta_faithfulness: float,
        delta_overreach_rate: float,
        high_risk_regression_count: int,
    ) -> str:
        if high_risk_regression_count > 0:
            return "harmful"

        if (
            delta_overreach_rate > self.harmful_risk_delta
            or delta_pass_rate <= self.harmful_quality_delta
            or delta_answer_correctness <= self.harmful_quality_delta
            or delta_faithfulness <= self.harmful_quality_delta
        ):
            return "harmful"

        quality_improved = any(
            delta >= self.beneficial_quality_delta
            for delta in (
                delta_answer_correctness,
                delta_pass_rate,
                delta_faithfulness,
            )
        )
        risk_stable = delta_overreach_rate <= 0.0

        if quality_improved and risk_stable:
            return "beneficial"

        return "neutral"

    def recommendation(
        self,
        *,
        verdict: str,
        metric_diffs: Mapping[str, float],
        bucket_analysis: Mapping[str, Any],
    ) -> str:
        if verdict == "beneficial":
            return "Promote the candidate run and inspect improved cases for reusable patterns."
        if verdict == "harmful":
            if bucket_analysis.get("high_risk_regression_count", 0) > 0:
                return "Do not promote the candidate run; inspect high-risk regressions before further rollout."
            return "Hold the candidate run and address quality or risk regressions before promotion."
        if metric_diffs.get("delta_pass_rate", 0.0) == 0.0:
            return "No material change detected; keep the baseline unless cost or latency changed elsewhere."
        return "Results are mixed; review improved and regressed cases before deciding on promotion."

    def _delta(
        self,
        baseline_summary: Mapping[str, Any],
        candidate_summary: Mapping[str, Any],
        metric_name: str,
    ) -> float:
        baseline_value = self._require_float(
            baseline_summary, metric_name, context="baseline_summary"
        )
        candidate_value = self._require_float(
            candidate_summary, metric_name, context="candidate_summary"
        )
        return candidate_value - baseline_value

    def _index_cases(
        self, cases: Sequence[Mapping[str, Any]] | Iterable[Mapping[str, Any]]
    ) -> dict[str, Mapping[str, Any]]:
        indexed: dict[str, Mapping[str, Any]] = {}
        for raw_case in cases:
            case = dict(raw_case)
            case_id = case.get("eval_case_id", case.get("id"))
            if case_id is None:
                raise ValueError("Each case must define 'eval_case_id' or 'id'")
            indexed[str(case_id)] = case
        return indexed

    def _compare_case_pair(
        self,
        *,
        case_id: str,
        baseline_case: Mapping[str, Any],
        candidate_case: Mapping[str, Any],
    ) -> dict[str, Any]:
        baseline_pass = self._require_bool(
            baseline_case, "pass", context=f"baseline_case[{case_id}]"
        )
        candidate_pass = self._require_bool(
            candidate_case, "pass", context=f"candidate_case[{case_id}]"
        )
        answer_delta = self._case_metric_delta(
            baseline_case, candidate_case, "answer_correctness"
        )
        faithfulness_delta = self._case_metric_delta(
            baseline_case, candidate_case, "faithfulness"
        )
        overreach_delta = self._case_metric_delta(
            baseline_case, candidate_case, "overreach", cast_bool=True
        )
        candidate_overreach = self._require_bool(
            candidate_case, "overreach", context=f"candidate_case[{case_id}]"
        )
        candidate_source_valid = self._require_bool(
            candidate_case, "source_valid", context=f"candidate_case[{case_id}]"
        )

        if candidate_pass and not baseline_pass:
            status = "improved"
        elif baseline_pass and not candidate_pass:
            status = "regressed"
        else:
            quality_regressed = any(
                delta is not None and delta < 0
                for delta in (answer_delta, faithfulness_delta)
            )
            risk_regressed = overreach_delta > 0
            quality_improved = any(
                delta is not None and delta > 0
                for delta in (answer_delta, faithfulness_delta)
            )

            if quality_regressed or risk_regressed:
                status = "regressed"
            elif quality_improved:
                status = "improved"
            else:
                status = "unchanged"

        high_risk = status == "regressed" and (
            candidate_overreach
            or not candidate_source_valid
            or (answer_delta is not None and answer_delta <= self.high_risk_answer_delta)
        )

        return {
            "eval_case_id": case_id,
            "status": status,
            "high_risk": high_risk,
            "delta_answer_correctness": answer_delta,
            "delta_faithfulness": faithfulness_delta,
            "delta_overreach": overreach_delta,
            "baseline": dict(baseline_case),
            "candidate": dict(candidate_case),
        }

    def _case_metric_delta(
        self,
        baseline_case: Mapping[str, Any],
        candidate_case: Mapping[str, Any],
        metric_name: str,
        *,
        cast_bool: bool = False,
    ) -> float | None:
        if cast_bool:
            baseline_value = self._require_bool(
                baseline_case, metric_name, context="baseline_case"
            )
            candidate_value = self._require_bool(
                candidate_case, metric_name, context="candidate_case"
            )
            return (1.0 if candidate_value else 0.0) - (
                1.0 if baseline_value else 0.0
            )

        baseline_value = self._coerce_optional_float(
            baseline_case.get(metric_name),
            field_name=metric_name,
            context="baseline_case",
        )
        candidate_value = self._coerce_optional_float(
            candidate_case.get(metric_name),
            field_name=metric_name,
            context="candidate_case",
        )
        if baseline_value is None or candidate_value is None:
            return None
        return candidate_value - baseline_value

    def _coerce_optional_float(
        self,
        value: Any,
        *,
        field_name: str,
        context: str,
    ) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{context}.{field_name} must be a number or None")
        return float(value)

    def _require_float(
        self,
        mapping: Mapping[str, Any],
        field_name: str,
        *,
        context: str,
    ) -> float:
        value = self._coerce_optional_float(
            mapping.get(field_name),
            field_name=field_name,
            context=context,
        )
        if value is None:
            raise ValueError(f"{context}.{field_name} is required")
        return value

    def _require_bool(
        self,
        mapping: Mapping[str, Any],
        field_name: str,
        *,
        context: str,
    ) -> bool:
        value = mapping.get(field_name)
        if isinstance(value, bool):
            return value
        raise ValueError(f"{context}.{field_name} must be a bool")
