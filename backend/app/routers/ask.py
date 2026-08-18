import json
import logging
from collections.abc import Generator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.generate import generate_answer
from app.schemas import AskRequest
from app.search import hybrid_search

router = APIRouter()
log = logging.getLogger("app.routers.ask")

NO_CONTEXT_MESSAGE = (
    "I couldn't find anything relevant to that in the React or Next.js docs I've indexed."
)
GENERATION_ERROR_MESSAGE = (
    "Sorry, I couldn't generate an answer just now — the language model provider "
    "returned an error. If you're running this yourself, check that LLM_API_KEY is set."
)


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream(db: Session, query: str, k: int) -> Generator[str, None, None]:
    results = hybrid_search(db, query, k=k)

    sources = [
        {"index": i + 1, "url": r.url, "heading_path": r.heading_path, "source": r.source}
        for i, r in enumerate(results)
    ]
    yield _sse("sources", sources)

    if not results:
        yield _sse("token", NO_CONTEXT_MESSAGE)
        yield _sse("done", {})
        return

    try:
        for token in generate_answer(query, results):
            yield _sse("token", token)
    except Exception:
        # A generator that's already started streaming a response can't turn
        # into an HTTP error status any more — the client would just see the
        # connection drop mid-response with no explanation. Surface the
        # failure as a normal 'token' event instead, so the UI can show it.
        log.exception("generation failed for query=%r", query)
        yield _sse("token", GENERATION_ERROR_MESSAGE)

    yield _sse("done", {})


@router.post("/ask")
def ask(request: AskRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    return StreamingResponse(_stream(db, request.query, request.k), media_type="text/event-stream")
