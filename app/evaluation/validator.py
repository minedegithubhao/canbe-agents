from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.generator import hash_answer, is_allowed_source_url
from app.evaluation.schemas import EvalCase


@dataclass(frozen=True)
class StaleCheckResult:
    case_id: str
    status: str
    reason: str = ""


def validate_stale_status(case: EvalCase, current_answers: dict[str, str]) -> StaleCheckResult:
    if not case.source_faq_ids:
        return StaleCheckResult(case_id=case.case_id, status="valid", reason="")
    for faq_id in case.source_faq_ids:
        current_answer = current_answers.get(faq_id)
        if current_answer is None:
            return StaleCheckResult(case_id=case.case_id, status="stale", reason=f"source FAQ missing: {faq_id}")
        if hash_answer(current_answer) != case.source_answer_hash:
            return StaleCheckResult(case_id=case.case_id, status="stale", reason=f"answer_clean hash changed: {faq_id}")
    return StaleCheckResult(case_id=case.case_id, status="valid", reason="")


def validate_case_structure(case: EvalCase) -> list[str]:
    errors: list[str] = []
    if not case.case_id:
        errors.append("case_id is required")
    if not case.question:
        errors.append("question is required")
    if not case.must_refuse and not case.source_faq_ids:
        errors.append("answerable case requires source_faq_ids")
    if case.must_refuse and case.expected_retrieved_faq_ids:
        errors.append("must_refuse case cannot require expected_retrieved_faq_ids")
    if not case.reference_answer:
        errors.append("reference_answer is required")
    if case.source_url and not is_allowed_source_url(case.source_url):
        errors.append("source_url is outside allowed JD help issue scope")
    return errors
