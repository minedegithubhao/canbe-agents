from sqlalchemy.engine import Engine

from app.repositories.mysql.base import Base
from app.repositories.mysql import models as _models
from app.repositories.mysql.session import create_mysql_engine


def bootstrap_schema(engine: Engine | None = None) -> None:
    target_engine = engine or create_mysql_engine()
    Base.metadata.create_all(target_engine)
