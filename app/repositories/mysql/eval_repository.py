from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.mysql.models import EvalCase, EvalSet


class EvalRepository:
    def __init__(self, session: Session | None):
        self.session = session

    def create(self, **kwargs) -> EvalSet:
        return self.create_eval_set(**kwargs)

    def create_eval_set(
        self,
        *,
        code: str,
        name: str,
        dataset_id: int | None = None,
        description: str | None = None,
        generation_strategy: str | None = None,
    ) -> EvalSet:
        eval_set = EvalSet(
            code=code,
            name=name,
            dataset_id=dataset_id,
            description=description,
            generation_strategy=generation_strategy,
        )
        self._session.add(eval_set)
        self._session.flush()
        return eval_set

    def list_eval_sets(self) -> list[EvalSet]:
        return list(self._session.query(EvalSet).order_by(EvalSet.id.asc()))

    def update_case(
        self,
        *,
        case_id: int,
        case_payload: dict[str, object],
    ) -> EvalCase:
        case = self._session.get(EvalCase, case_id)
        if case is None:
            raise ValueError(f"EvalCase not found: {case_id}")

        case.query = str(case_payload["query"])
        case.expected_answer = (
            None
            if case_payload.get("expected_answer") is None
            else str(case_payload["expected_answer"])
        )
        case.expected_sources_json = dict(case_payload.get("expected_sources_json") or {})
        case.labels_json = dict(case_payload.get("labels") or {})
        case.difficulty = (
            None
            if case_payload.get("difficulty") is None
            else str(case_payload["difficulty"])
        )
        case.source_type = (
            None
            if case_payload.get("source_type") is None
            else str(case_payload["source_type"])
        )
        case.source_ref = (
            None
            if case_payload.get("external_id") is None
            else str(case_payload["external_id"])
        )
        case.behavior_json = dict(case_payload.get("behavior") or {})
        case.scoring_profile_json = dict(case_payload.get("scoring_profile") or {})
        case.enabled = bool(case_payload.get("enabled", True))
        self._session.flush()
        return case

    def add_case(
        self,
        *,
        eval_set_id: int,
        case_payload: dict[str, object] | None = None,
        query: str | None = None,
        expected_answer: str | None = None,
        case_no: int = 1,
        expected_sources_json: dict | None = None,
        labels_json: dict | None = None,
        difficulty: str | None = None,
        source_type: str | None = None,
        source_ref: str | None = None,
        behavior_json: dict | None = None,
        scoring_profile_json: dict | None = None,
        enabled: bool = True,
    ) -> EvalCase:
        payload = case_payload or {}
        case = EvalCase(
            eval_set_id=eval_set_id,
            query=str(payload.get("query") if payload else query),
            expected_answer=(
                None
                if (payload.get("expected_answer") if payload else expected_answer) is None
                else str(payload.get("expected_answer") if payload else expected_answer)
            ),
            case_no=int(payload.get("case_no", case_no)),
            expected_sources_json=dict(payload.get("expected_sources_json") or expected_sources_json or {}),
            labels_json=dict(payload.get("labels") or labels_json or {}),
            difficulty=(
                None
                if (payload.get("difficulty") if payload else difficulty) is None
                else str(payload.get("difficulty") if payload else difficulty)
            ),
            source_type=(
                None
                if (payload.get("source_type") if payload else source_type) is None
                else str(payload.get("source_type") if payload else source_type)
            ),
            source_ref=(
                None
                if (payload.get("external_id") if payload else source_ref) is None
                else str(payload.get("external_id") if payload else source_ref)
            ),
            behavior_json=dict(payload.get("behavior") or behavior_json or {}),
            scoring_profile_json=dict(payload.get("scoring_profile") or scoring_profile_json or {}),
            enabled=bool(payload.get("enabled", enabled)),
        )
        self._session.add(case)
        self._session.flush()
        return case

    def list_cases(self, eval_set_id: int) -> list[EvalCase]:
        statement = (
            select(EvalCase)
            .where(EvalCase.eval_set_id == eval_set_id)
            .order_by(EvalCase.case_no.asc(), EvalCase.id.asc())
        )
        return list(self._session.scalars(statement))

    def list(self, eval_set_id: int) -> list[EvalCase]:
        return self.list_cases(eval_set_id)

    @property
    def _session(self) -> Session:
        if self.session is None:
            raise ValueError("EvalRepository requires a session for persistence operations")
        return self.session
