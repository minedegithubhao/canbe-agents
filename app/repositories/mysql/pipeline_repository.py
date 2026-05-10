from sqlalchemy.orm import Session

from app.repositories.mysql.models import Pipeline, PipelineVersion


class PipelineRepository:
    def __init__(self, session: Session | None):
        self.session = session

    def create(self, **kwargs) -> Pipeline:
        return self.create_pipeline(**kwargs)

    def create_pipeline(
        self,
        *,
        code: str,
        name: str,
        description: str | None = None,
    ) -> Pipeline:
        pipeline = Pipeline(code=code, name=name, description=description)
        self._session.add(pipeline)
        self._session.flush()
        return pipeline

    def list_pipelines(self) -> list[Pipeline]:
        return list(self._session.query(Pipeline).order_by(Pipeline.id.asc()))

    def create_pipeline_version(
        self,
        *,
        pipeline_id: int,
        version_no: int,
        chunking_config_json: dict,
        retrieval_config_json: dict,
        recall_config_json: dict,
        rerank_config_json: dict,
        prompt_config_json: dict,
        fallback_config_json: dict,
        status: str = "draft",
    ) -> PipelineVersion:
        version = PipelineVersion(
            pipeline_id=pipeline_id,
            version_no=version_no,
            chunking_config_json=chunking_config_json,
            retrieval_config_json=retrieval_config_json,
            recall_config_json=recall_config_json,
            rerank_config_json=rerank_config_json,
            prompt_config_json=prompt_config_json,
            fallback_config_json=fallback_config_json,
            status=status,
        )
        self._session.add(version)
        self._session.flush()
        return version

    def create_version(self, **kwargs) -> PipelineVersion:
        return self.create_pipeline_version(**kwargs)

    def freeze_version(self, pipeline_version_id: int) -> PipelineVersion:
        version = self._session.get(PipelineVersion, pipeline_version_id)
        if version is None:
            raise ValueError(f"PipelineVersion not found: {pipeline_version_id}")
        version.status = "frozen"
        self._session.flush()
        return version

    @property
    def _session(self) -> Session:
        if self.session is None:
            raise ValueError("PipelineRepository requires a session for persistence operations")
        return self.session
