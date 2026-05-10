import pytest

from app.services.comparison_service import ComparisonService


def test_verdict_marks_beneficial_when_quality_improves_without_risk_spike():
    service = ComparisonService()

    verdict = service.verdict(
        delta_answer_correctness=0.05,
        delta_pass_rate=0.04,
        delta_faithfulness=0.00,
        delta_overreach_rate=0.00,
        high_risk_regression_count=0,
    )

    assert verdict == "beneficial"


def test_verdict_marks_harmful_when_quality_regresses_even_if_another_metric_improves():
    service = ComparisonService()

    verdict = service.verdict(
        delta_answer_correctness=-0.03,
        delta_pass_rate=0.02,
        delta_faithfulness=0.00,
        delta_overreach_rate=0.00,
        high_risk_regression_count=0,
    )

    assert verdict == "harmful"


def test_verdict_marks_neutral_for_small_quality_gain_with_small_risk_increase():
    service = ComparisonService()

    verdict = service.verdict(
        delta_answer_correctness=0.009,
        delta_pass_rate=0.00,
        delta_faithfulness=0.00,
        delta_overreach_rate=0.01,
        high_risk_regression_count=0,
    )

    assert verdict == "neutral"


def test_verdict_boundary_thresholds_are_explicit():
    service = ComparisonService()

    assert (
        service.verdict(
            delta_answer_correctness=service.beneficial_quality_delta,
            delta_pass_rate=0.00,
            delta_faithfulness=0.00,
            delta_overreach_rate=0.00,
            high_risk_regression_count=0,
        )
        == "beneficial"
    )
    assert (
        service.verdict(
            delta_answer_correctness=0.00,
            delta_pass_rate=service.harmful_quality_delta,
            delta_faithfulness=0.00,
            delta_overreach_rate=0.00,
            high_risk_regression_count=0,
        )
        == "harmful"
    )
    assert (
        service.verdict(
            delta_answer_correctness=0.00,
            delta_pass_rate=0.00,
            delta_faithfulness=0.00,
            delta_overreach_rate=service.harmful_risk_delta,
            high_risk_regression_count=0,
        )
        == "neutral"
    )


def test_compare_case_pair_marks_regressed_when_quality_loss_outweighs_small_improvement():
    service = ComparisonService()

    comparison = service._compare_case_pair(
        case_id="case-1",
        baseline_case={
            "eval_case_id": "case-1",
            "pass": True,
            "answer_correctness": 0.90,
            "faithfulness": 0.80,
            "overreach": False,
            "source_valid": True,
        },
        candidate_case={
            "eval_case_id": "case-1",
            "pass": True,
            "answer_correctness": 0.70,
            "faithfulness": 0.81,
            "overreach": False,
            "source_valid": True,
        },
    )

    assert comparison["status"] == "regressed"
    assert comparison["delta_answer_correctness"] == pytest.approx(-0.20)
    assert comparison["delta_faithfulness"] == pytest.approx(0.01)


def test_analyze_case_buckets_extracts_improved_regressed_and_high_risk_regressions():
    service = ComparisonService()

    bucket_analysis = service.analyze_case_buckets(
        baseline_cases=[
            {
                "eval_case_id": "improved",
                "pass": False,
                "answer_correctness": 0.20,
                "faithfulness": 0.30,
                "overreach": False,
                "source_valid": True,
            },
            {
                "eval_case_id": "regressed",
                "pass": True,
                "answer_correctness": 0.80,
                "faithfulness": 0.70,
                "overreach": False,
                "source_valid": True,
            },
            {
                "eval_case_id": "high-risk",
                "pass": True,
                "answer_correctness": 0.90,
                "faithfulness": 0.85,
                "overreach": False,
                "source_valid": True,
            },
            {
                "eval_case_id": "baseline-only",
                "pass": True,
                "answer_correctness": 0.50,
                "faithfulness": 0.50,
                "overreach": False,
                "source_valid": True,
            },
        ],
        candidate_cases=[
            {
                "eval_case_id": "improved",
                "pass": True,
                "answer_correctness": 0.60,
                "faithfulness": 0.50,
                "overreach": False,
                "source_valid": True,
            },
            {
                "eval_case_id": "regressed",
                "pass": False,
                "answer_correctness": 0.75,
                "faithfulness": 0.65,
                "overreach": False,
                "source_valid": True,
            },
            {
                "eval_case_id": "high-risk",
                "pass": True,
                "answer_correctness": 0.60,
                "faithfulness": 0.85,
                "overreach": True,
                "source_valid": False,
            },
            {
                "eval_case_id": "candidate-only",
                "pass": True,
                "answer_correctness": 0.90,
                "faithfulness": 0.90,
                "overreach": False,
                "source_valid": True,
            },
        ],
    )

    assert bucket_analysis["improved_case_count"] == 1
    assert [case["eval_case_id"] for case in bucket_analysis["improved_cases"]] == [
        "improved"
    ]
    assert bucket_analysis["regressed_case_count"] == 2
    assert [case["eval_case_id"] for case in bucket_analysis["regressed_cases"]] == [
        "high-risk",
        "regressed",
    ]
    assert bucket_analysis["high_risk_regression_count"] == 1
    assert [
        case["eval_case_id"] for case in bucket_analysis["high_risk_regressions"]
    ] == ["high-risk"]
    assert bucket_analysis["baseline_only_case_count"] == 1
    assert bucket_analysis["candidate_only_case_count"] == 1


def test_compare_runs_keeps_case_lists_under_bucket_analysis_only():
    service = ComparisonService()

    result = service.compare_runs(
        baseline_summary={
            "pass_rate": 0.50,
            "answer_correctness_avg": 0.50,
            "faithfulness_avg": 0.50,
            "source_grounding_avg": 0.50,
            "fallback_rate": 0.10,
            "source_valid_rate": 0.90,
            "overreach_rate": 0.10,
        },
        candidate_summary={
            "pass_rate": 0.60,
            "answer_correctness_avg": 0.60,
            "faithfulness_avg": 0.55,
            "source_grounding_avg": 0.55,
            "fallback_rate": 0.08,
            "source_valid_rate": 0.92,
            "overreach_rate": 0.10,
        },
        baseline_cases=[],
        candidate_cases=[],
    )

    assert set(result) == {
        "metric_diffs",
        "bucket_analysis",
        "verdict",
        "recommendation",
    }
    assert "improved_cases" not in result
    assert "regressed_cases" not in result


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pass", "yes"),
        ("pass", 1),
        ("overreach", "false"),
        ("source_valid", 0),
    ],
)
def test_compare_case_pair_rejects_non_boolean_fields(field, value):
    service = ComparisonService()
    baseline_case = {
        "eval_case_id": "case-1",
        "pass": True,
        "answer_correctness": 0.5,
        "faithfulness": 0.5,
        "overreach": False,
        "source_valid": True,
    }
    candidate_case = dict(baseline_case)
    candidate_case[field] = value

    with pytest.raises(ValueError, match=field):
        service._compare_case_pair(
            case_id="case-1",
            baseline_case=baseline_case,
            candidate_case=candidate_case,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("answer_correctness", "bad"),
        ("faithfulness", object()),
    ],
)
def test_compare_case_pair_rejects_non_numeric_case_metrics(field, value):
    service = ComparisonService()
    baseline_case = {
        "eval_case_id": "case-1",
        "pass": True,
        "answer_correctness": 0.5,
        "faithfulness": 0.5,
        "overreach": False,
        "source_valid": True,
    }
    candidate_case = dict(baseline_case)
    candidate_case[field] = value

    with pytest.raises(ValueError, match=field):
        service._compare_case_pair(
            case_id="case-1",
            baseline_case=baseline_case,
            candidate_case=candidate_case,
        )


def test_compare_case_pair_treats_missing_quality_metrics_as_unknown_not_zero():
    service = ComparisonService()

    comparison = service._compare_case_pair(
        case_id="case-1",
        baseline_case={
            "eval_case_id": "case-1",
            "pass": True,
            "answer_correctness": None,
            "faithfulness": 0.5,
            "overreach": False,
            "source_valid": True,
        },
        candidate_case={
            "eval_case_id": "case-1",
            "pass": True,
            "answer_correctness": None,
            "faithfulness": 0.5,
            "overreach": False,
            "source_valid": True,
        },
    )

    assert comparison["status"] == "unchanged"
    assert comparison["delta_answer_correctness"] is None


def test_compare_runs_rejects_missing_summary_metrics_instead_of_assuming_zero():
    service = ComparisonService()

    with pytest.raises(ValueError, match="answer_correctness_avg"):
        service.compare_runs(
            baseline_summary={
                "pass_rate": 0.50,
                "faithfulness_avg": 0.50,
                "source_grounding_avg": 0.50,
                "fallback_rate": 0.10,
                "source_valid_rate": 0.90,
                "overreach_rate": 0.10,
            },
            candidate_summary={
                "pass_rate": 0.60,
                "answer_correctness_avg": 0.60,
                "faithfulness_avg": 0.55,
                "source_grounding_avg": 0.55,
                "fallback_rate": 0.08,
                "source_valid_rate": 0.92,
                "overreach_rate": 0.10,
            },
            baseline_cases=[],
            candidate_cases=[],
        )
