from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from cleanroom.database.models import Base


def create_db_engine(url: str) -> Engine:
    kwargs = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=kwargs)


def initialize_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
