from __future__ import annotations

from app.evaluation.generator import hash_answer
from app.evaluation.schemas import EvalCase
from app.evaluation.validator import StaleCheckResult, validate_case_structure, validate_stale_status


def make_case(source_hash: str) -> EvalCase:
    return EvalCase(
        case_id="faq_eval_000001",
        source_faq_ids=["FAQ_001"],
        category="订单相关",
        category_l1="订单相关",
        category_l2="订单修改",
        category_l3="规格修改",
        question="下单后还能改规格吗？",
        question_style="口语化改写",
        eval_type="单FAQ语义等价",
        difficulty="easy",
        expected_route_category="订单相关",
        expected_retrieved_faq_ids=["FAQ_001"],
        reference_answer="未支付可取消重拍。",
        key_points=["未支付可取消重拍"],
        forbidden_points=[],
        must_refuse=False,
        source_url="https://help.jd.com/user/issue/292-553.html",
        source_answer_hash=source_hash,
        validation_status="validated",
    )


def test_validate_stale_status_marks_case_valid_when_answer_hash_matches():
    answer = "未支付可取消重拍。"
    case = make_case(hash_answer(answer))
    current_answers = {"FAQ_001": answer}

    result = validate_stale_status(case, current_answers)

    assert result == StaleCheckResult(case_id="faq_eval_000001", status="valid", reason="")


def test_validate_stale_status_marks_case_stale_when_answer_hash_changed():
    case = make_case(hash_answer("旧答案"))
    current_answers = {"FAQ_001": "新答案"}

    result = validate_stale_status(case, current_answers)

    assert result.status == "stale"
    assert "answer_clean hash changed" in result.reason


def test_validate_case_structure_rejects_refusal_case_with_expected_faq_ids():
    case = make_case(hash_answer("未支付可取消重拍。"))
    case.must_refuse = True

    errors = validate_case_structure(case)

    assert "must_refuse case cannot require expected_retrieved_faq_ids" in errors
