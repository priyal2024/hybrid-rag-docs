from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Computed, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

EMBEDDING_DIM = 384  # sentence-transformers/all-MiniLM-L6-v2


class Chunk(Base):
    """One retrieval unit: a heading-bounded slice of a doc page, indexed both
    as a dense vector (semantic search) and a Postgres tsvector (keyword
    search) — the two signals hybrid search fuses at query time.
    """

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    source: Mapped[str] = mapped_column(String(32), nullable=False)          # "react" | "nextjs"
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)      # repo-relative path
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    heading_path: Mapped[str] = mapped_column(String(512), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Generated column: Postgres maintains this automatically from `content`,
    # so ingestion never has to remember to keep it in sync.
    content_tsv = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', content)", persisted=True),
        nullable=True,
    )

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    # sha256 of (source, file_path, chunk_index, content) — makes re-ingestion
    # idempotent via upsert instead of accumulating duplicate rows.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
