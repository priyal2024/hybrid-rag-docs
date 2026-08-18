"""The /ask endpoint's LLM-generation path needs a real LLM_API_KEY (Groq or
OpenAI) to exercise end-to-end, which isn't available in this environment —
those tests are skipped rather than mocked, so a green run here means "the
no-context path and the wiring are verified," not "generation was tested
against a live model." Set LLM_API_KEY and remove the skip to run for real.
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import get_db
from app.main import app

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


def _parse_sse(body: str) -> list[tuple[str, object]]:
    events = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = block.splitlines()
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((event, data))
    return events


def test_ask_returns_no_context_message_when_corpus_empty(db_session):
    response = client.post("/ask", json={"query": "anything", "k": 3})
    assert response.status_code == 200

    events = _parse_sse(response.text)
    kinds = [e for e, _ in events]
    assert kinds == ["sources", "token", "done"]
    assert events[0][1] == []  # no sources found
    assert "couldn't find" in events[1][1]


@pytest.mark.skipif(not settings.llm_api_key, reason="LLM_API_KEY not set — skipping live generation test")
def test_ask_streams_generated_answer_with_sources(db_session):
    import hashlib

    from app.embeddings import embed_query
    from app.models import Chunk

    content = "useEffect lets you synchronize a component with an external system."
    db_session.add(
        Chunk(
            source="react",
            file_path="src/content/test.md",
            url="https://react.dev/reference/react/useEffect",
            heading_path="useEffect",
            chunk_index=0,
            content=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            embedding=embed_query(content),
        )
    )
    db_session.commit()

    response = client.post("/ask", json={"query": "what does useEffect do?", "k": 3})
    events = _parse_sse(response.text)

    assert events[0][0] == "sources"
    assert len(events[0][1]) >= 1
    token_events = [d for e, d in events if e == "token"]
    assert "".join(token_events).strip()
    assert events[-1][0] == "done"
