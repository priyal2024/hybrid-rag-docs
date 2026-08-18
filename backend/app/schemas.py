from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    k: int = Field(default=8, ge=1, le=50)


class SearchResultItem(BaseModel):
    id: int
    source: str
    url: str
    heading_path: str
    content: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    cached: bool
