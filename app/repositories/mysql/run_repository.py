from sqlalchemy.orm import Session

from app.repositories.mysql.models import CaseResult, ExperimentRun


class RunRepository:
    def __init__(self, session: Session | None):
        self.session = session

    def create(self, **kwargs) -> ExperimentRun:
        return self.create_run(**kwargs)

    def create_run(
        self,
        *,
        dataset_version_id: int,
        pipeline_version_id: int,
        eval_set_id: int,
        run_no: int,
        status: str = "draft",
        triggered_by: str | None = None,
    ) -> ExperimentRun:
        run = ExperimentRun(
            dataset_version_id=dataset_version_id,
            pipeline_version_id=pipeline_version_id,
            eval_set_id=eval_set_id,
            run_no=run_no,
            status=status,
            triggered_by=triggered_by,
        )
        self._session.add(run)
        self._session.flush()
        return run

    def list_runs(self) -> list[ExperimentRun]:
        return list(self._session.query(ExperimentRun).order_by(ExperimentRun.id.asc()))

    def get_run_summary(self, run_id: int) -> ExperimentRun:
        return self._require_run(run_id)

    def get_case_trace(self, run_id: int, case_id: int) -> dict:
        result = (
            self._session.query(CaseResult)
            .filter(
                CaseResult.experiment_run_id == run_id,
                CaseResult.eval_case_id == case_id,
            )
            .one_or_none()
        )
        if result is None:
            raise ValueError(f"CaseResult not found: run_id={run_id}, case_id={case_id}")
        return {
            "experiment_run_id": result.experiment_run_id,
            "eval_case_id": result.eval_case_id,
            "trace_artifact_id": result.trace_artifact_id,
            "judgement_json": result.judgement_json,
        }

    def update_status(self, experiment_run_id: int, status: str) -> ExperimentRun:
        run = self._require_run(experiment_run_id)
        run.status = status
        self._session.flush()
        return run

    def save_case_result(
        self,
        *,
        experiment_run_id: int,
        eval_case_id: int,
        status: str,
        fallback: bool = False,
        answer: str | None = None,
        confidence: float | None = None,
        retrieval_score: float | None = None,
        rerank_score: float | None = None,
        judgement_json: dict | None = None,
        trace_artifact_id: int | None = None,
    ) -> CaseResult:
        result = CaseResult(
            experiment_run_id=experiment_run_id,
            eval_case_id=eval_case_id,
            status=status,
            fallback=fallback,
            answer=answer,
            confidence=confidence,
            retrieval_score=retrieval_score,
            rerank_score=rerank_score,
            judgement_json=judgement_json or {},
            trace_artifact_id=trace_artifact_id,
        )
        self._session.add(result)
        self._session.flush()
        return result

    def save_summary(self, experiment_run_id: int, summary_json: dict) -> ExperimentRun:
        run = self._require_run(experiment_run_id)
        run.summary_json = summary_json
        self._session.flush()
        return run

    def _require_run(self, experiment_run_id: int) -> ExperimentRun:
        run = self._session.get(ExperimentRun, experiment_run_id)
        if run is None:
            raise ValueError(f"ExperimentRun not found: {experiment_run_id}")
        return run

    @property
    def _session(self) -> Session:
        if self.session is None:
            raise ValueError("RunRepository requires a session for persistence operations")
        return self.session
