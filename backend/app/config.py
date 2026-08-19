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
    llm_model: str = "openai/gpt-oss-120b"

    # Comma-separated in the env var, e.g. "https://a.com,https://b.com".
    # Deliberately typed as `str`, not `list[str]`: pydantic-settings' default
    # behavior for list-typed fields is to JSON-decode the raw env var value
    # *before* any field_validator gets a chance to run — which blows up on a
    # plain string like "http://localhost:3000" (not valid JSON). Found this
    # the hard way: it works fine with no env var set at all (the Python-list
    # default never goes through env parsing), but crashes the moment a real
    # deployment's ConfigMap actually sets one as a plain string. Splitting it
    # ourselves in a property sidesteps pydantic-settings' complex-type
    # handling entirely instead of fighting it.
    cors_allow_origins_raw: str = "http://localhost:3000"

    @property
    def cors_allow_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins_raw.split(",") if o.strip()]


settings = Settings()
