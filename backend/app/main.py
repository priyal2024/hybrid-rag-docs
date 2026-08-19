from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ask, search, upload

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router)
app.include_router(ask.router)
app.include_router(upload.router)


@app.get("/health")
def health() -> dict:
    """Liveness/readiness probe target for Docker/K8s."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs"}
