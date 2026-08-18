import json
from collections.abc import Generator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.generate import generate_answer
from app.schemas import AskRequest
from app.search import hybrid_search

router = APIRouter()

NO_CONTEXT_MESSAGE = (
    "I couldn't find anything relevant to that in the React or Next.js docs I've indexed."
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

    for token in generate_answer(query, results):
        yield _sse("token", token)
    yield _sse("done", {})


@router.post("/ask")
def ask(request: AskRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    return StreamingResponse(_stream(db, request.query, request.k), media_type="text/event-stream")
