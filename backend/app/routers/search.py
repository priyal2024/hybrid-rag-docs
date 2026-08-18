from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.cache import get_cached_search, set_cached_search
from app.db import get_db
from app.schemas import SearchRequest, SearchResponse, SearchResultItem
from app.search import hybrid_search

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
def search(request: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    cached = get_cached_search(request.query, request.k)
    if cached is not None:
        return SearchResponse(query=request.query, results=[SearchResultItem(**r) for r in cached], cached=True)

    results = hybrid_search(db, request.query, k=request.k)
    items = [
        SearchResultItem(
            id=r.id, source=r.source, url=r.url, heading_path=r.heading_path, content=r.content, score=r.score
        )
        for r in results
    ]
    set_cached_search(request.query, request.k, [item.model_dump() for item in items])
    return SearchResponse(query=request.query, results=items, cached=False)
