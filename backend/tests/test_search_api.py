import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.cache import get_redis
from app.config import settings
from app.db import get_db
from app.embeddings import embed_query
from app.main import app
from app.models import Chunk

test_engine = create_engine(settings.test_database_url)
TestSession = sessionmaker(bind=test_engine)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_search_cache():
    yield
    get_redis().flushdb()


def test_search_endpoint_returns_results_and_caches(db_session):
    content = "useEffect lets you synchronize a component with an external system."
    chunk = Chunk(
        source="react",
        file_path="src/content/test.md",
        url="https://react.dev/reference/react/useEffect",
        heading_path="useEffect",
        chunk_index=0,
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        embedding=embed_query(content),
    )
    db_session.add(chunk)
    db_session.commit()

    response = client.post("/search", json={"query": "useEffect", "k": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is False
    assert len(body["results"]) >= 1
    assert body["results"][0]["url"] == "https://react.dev/reference/react/useEffect"

    # Second identical request should be served from the Redis cache.
    response2 = client.post("/search", json={"query": "useEffect", "k": 5})
    assert response2.status_code == 200
    assert response2.json()["cached"] is True
    assert response2.json()["results"] == body["results"]


def test_search_endpoint_validates_input():
    response = client.post("/search", json={"query": "", "k": 5})
    assert response.status_code == 422

    response = client.post("/search", json={"query": "ok", "k": 0})
    assert response.status_code == 422
