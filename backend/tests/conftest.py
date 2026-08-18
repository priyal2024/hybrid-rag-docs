"""Test DB fixtures.

Deliberately bound to `settings.test_database_url`, never `settings.database_url`
— these fixtures truncate tables between tests, and must never be able to
reach the real ingested corpus.
"""
import os

# Standard hygiene for running the tokenizers lib under a test runner —
# harmless either way, avoids a known (if not what tripped us here) class of
# fork-related warnings.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.embeddings import get_embedding_model

BACKEND_DIR_ALEMBIC_INI = __file__.rsplit("/tests/", 1)[0] + "/alembic.ini"

# Load the embedding model once here, at conftest import time, before any
# test needs it — first-load cost (reading weights off disk) shouldn't be
# attributed to whichever test happens to run first.
get_embedding_model()


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
    # DELETE, not TRUNCATE: TRUNCATE needs an ACCESS EXCLUSIVE lock, which
    # blocks against *any* concurrent transaction on the table — including a
    # previous test's HTTP request still finishing on Starlette's threadpool
    # (sync routes run off-thread) a few milliseconds after the test itself
    # returned. DELETE only needs a row-level lock, which Postgres's MVCC
    # lets run concurrently with a plain SELECT — no test-boundary race.
    session.execute(text("DELETE FROM chunks"))
    session.commit()
    yield session
    session.rollback()
    session.close()
    engine.dispose()
