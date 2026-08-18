"""Test DB fixtures.

Deliberately bound to `settings.test_database_url`, never `settings.database_url`
— these fixtures truncate tables between tests, and must never be able to
reach the real ingested corpus.
"""
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings

BACKEND_DIR_ALEMBIC_INI = __file__.rsplit("/tests/", 1)[0] + "/alembic.ini"


def _db_reachable(url: str) -> bool:
    try:
        engine = create_engine(url)
        with engine.connect():
            pass
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def _migrated_test_db():
    if not _db_reachable(settings.test_database_url):
        pytest.skip("test database not reachable — skipping DB-backed tests", allow_module_level=True)

    cfg = Config(BACKEND_DIR_ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", settings.test_database_url)
    command.upgrade(cfg, "head")


@pytest.fixture
def db_session():
    engine = create_engine(settings.test_database_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.execute(text("TRUNCATE TABLE chunks RESTART IDENTITY"))
    session.commit()
    yield session
    session.rollback()
    session.close()
    engine.dispose()
