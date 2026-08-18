"""Centralized app configuration, loaded from environment variables.

Kept deliberately small in M0 — grows as ingestion, search, and auth land.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "hybrid-rag-docs"
    environment: str = "development"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/hybrid_rag_docs"
    # Deliberately separate from database_url: tests truncate/rewrite data,
    # and must never be able to touch the real ingested corpus.
    test_database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/hybrid_rag_docs_test"
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap_servers: str = "localhost:9092"

    # Generation provider — OpenAI-compatible client pointed at Groq's free tier by
    # default. Swap base_url/api_key to point at real OpenAI with no code changes.
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model: str = "llama-3.1-8b-instant"


settings = Settings()
