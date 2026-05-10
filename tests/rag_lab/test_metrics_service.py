from app.services.judgement_service import JudgementService
from app.services.metrics_service import MetricsService


def test_judgement_service_builds_discrete_verdict_for_passing_case():
    service = JudgementService()

    verdict = service.discrete_verdict(
        answer_correctness=0.82,
        source_valid=True,
        overreach=False,
        fallback_correct=True,
    )

    assert verdict["pass"] is True
    assert verdict["failed_checks"] == []
    assert verdict["thresholds"] == {
        "answer_correctness_pass_threshold": 0.8,
    }
    assert verdict["metrics"] == [
        {
            "metric_name": "answer_correctness",
            "score": 0.82,
            "passed": True,
            "reason": None,
            "metadata": {},
        },
        {
            "metric_name": "source_valid",
            "score": None,
            "passed": True,
            "reason": None,
            "metadata": {},
        },
        {
            "metric_name": "overreach",
            "score": None,
            "passed": True,
            "reason": None,
            "metadata": {},
        },
        {
            "metric_name": "fallback_correct",
            "score": None,
            "passed": True,
            "reason": None,
            "metadata": {},
        },
    ]


def test_judgement_service_builds_discrete_verdict_for_failing_case():
    service = JudgementService(answer_correctness_pass_threshold=0.9)

    verdict = service.discrete_verdict(
        answer_correctness=0.82,
        source_valid=False,
        overreach=True,
        fallback_correct=False,
    )

    assert verdict["pass"] is False
    assert verdict["failed_checks"] == [
        "answer_correctness",
        "source_valid",
        "overreach",
        "fallback_correct",
    ]
    assert verdict["thresholds"] == {
        "answer_correctness_pass_threshold": 0.9,
    }
    assert [metric["metric_name"] for metric in verdict["metrics"]] == [
        "answer_correctness",
        "source_valid",
        "overreach",
        "fallback_correct",
    ]
    assert [metric["passed"] for metric in verdict["metrics"]] == [
        False,
        False,
        False,
        False,
    ]
    assert verdict["metrics"] == [
        {
            "metric_name": "answer_correctness",
            "score": 0.82,
            "passed": False,
            "reason": "below_threshold",
            "metadata": {},
        },
        {
            "metric_name": "source_valid",
            "score": None,
            "passed": False,
            "reason": "invalid_source",
            "metadata": {},
        },
        {
            "metric_name": "overreach",
            "score": None,
            "passed": False,
            "reason": "overreach_detected",
            "metadata": {},
        },
        {
            "metric_name": "fallback_correct",
            "score": None,
            "passed": False,
            "reason": "fallback_incorrect",
            "metadata": {},
        },
    ]


def test_metrics_service_aggregate_run_accepts_judgement_service_verdicts():
    judgement_service = JudgementService(answer_correctness_pass_threshold=0.8)
    metrics_service = MetricsService()

    case_results = [
        judgement_service.discrete_verdict(
            answer_correctness=0.92,
            source_valid=True,
            overreach=False,
            fallback_correct=True,
        ),
        judgement_service.discrete_verdict(
            answer_correctness=0.4,
            source_valid=False,
            overreach=True,
            fallback_correct=False,
        ),
    ]

    aggregated = metrics_service.aggregate_run(case_results)

    assert aggregated == {
        "case_count": 2,
        "pass_count": 1,
        "pass_rate": 0.5,
        "fallback_count": 1,
        "fallback_rate": 0.5,
        "overreach_count": 1,
        "overreach_rate": 0.5,
        "source_valid_rate": 0.5,
        "answer_correctness_avg": 0.66,
        "faithfulness_avg": None,
        "source_grounding_avg": None,
    }


def test_metrics_service_aggregate_run_uses_fallback_correct_as_canonical_field():
    service = MetricsService()

    aggregated = service.aggregate_run(
        [
            {"pass": True, "fallback_correct": True},
            {"pass": False, "fallback_correct": False},
        ]
    )

    assert aggregated["fallback_count"] == 1
    assert aggregated["fallback_rate"] == 0.5


def test_metrics_service_aggregate_run_supports_legacy_fallback_field():
    service = MetricsService()

    aggregated = service.aggregate_run(
        [
            {"pass": True, "fallback": True},
            {"pass": False, "fallback": False},
        ]
    )

    assert aggregated["fallback_count"] == 1
    assert aggregated["fallback_rate"] == 0.5


def test_metrics_service_aggregate_run_rejects_conflicting_fallback_fields():
    service = MetricsService()

    try:
        service.aggregate_run(
            [
                {
                    "pass": True,
                    "fallback": True,
                    "fallback_correct": False,
                }
            ]
        )
    except ValueError as exc:
        assert "fallback" in str(exc)
        assert "fallback_correct" in str(exc)
    else:
        raise AssertionError("Expected conflicting fallback fields to raise ValueError")


def test_metrics_service_aggregate_run_treats_missing_fallback_fields_as_absent():
    service = MetricsService()

    aggregated = service.aggregate_run(
        [
            {"pass": True},
            {"pass": False, "fallback_correct": True},
        ]
    )

    assert aggregated["fallback_count"] == 1
    assert aggregated["fallback_rate"] == 0.5
