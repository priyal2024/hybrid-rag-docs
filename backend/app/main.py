from fastapi import FastAPI

from app.config import settings
from app.routers import ask, search

app = FastAPI(title=settings.app_name)
app.include_router(search.router)
app.include_router(ask.router)


@app.get("/health")
def health() -> dict:
    """Liveness/readiness probe target for Docker/K8s."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs"}
