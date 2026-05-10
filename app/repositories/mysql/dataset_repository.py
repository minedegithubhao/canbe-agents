from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories.mysql.models import Dataset, DatasetVersion


class DatasetRepository:
    def __init__(self, session: Session | None):
        self.session = session

    def create(self, **kwargs) -> Dataset:
        return self.create_dataset(**kwargs)

    def create_dataset(
        self,
        *,
        code: str,
        name: str,
        knowledge_type: str | None = None,
        description: str | None = None,
    ) -> Dataset:
        dataset = Dataset(
            code=code,
            name=name,
            knowledge_type=knowledge_type,
            description=description,
        )
        self._session.add(dataset)
        self._session.flush()
        return dataset

    def list_datasets(self) -> list[Dataset]:
        statement = select(Dataset).order_by(Dataset.id.asc())
        return list(self._session.scalars(statement))

    def list(self) -> list[Dataset]:
        return self.list_datasets()

    def get_dataset(self, dataset_id: int) -> Dataset | None:
        return self._session.get(Dataset, dataset_id)

    def get(self, dataset_id: int) -> Dataset | None:
        return self.get_dataset(dataset_id)

    def create_version(self, **kwargs) -> DatasetVersion:
        return self.create_dataset_version(**kwargs)

    def create_dataset_version(
        self,
        *,
        dataset_id: int,
        version_no: int,
        source_type: str | None = None,
        source_uri: str | None = None,
        status: str = "draft",
        document_count: int = 0,
        chunk_count: int = 0,
        metadata_json: dict | None = None,
    ) -> DatasetVersion:
        version = DatasetVersion(
            dataset_id=dataset_id,
            version_no=version_no,
            source_type=source_type,
            source_uri=source_uri,
            status=status,
            document_count=document_count,
            chunk_count=chunk_count,
            metadata_json=metadata_json or {},
        )
        self._session.add(version)
        self._session.flush()
        return version

    @property
    def _session(self) -> Session:
        if self.session is None:
            raise ValueError("DatasetRepository requires a session for persistence operations")
        return self.session
