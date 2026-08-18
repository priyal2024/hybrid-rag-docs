"""Consumes `doc-chunks` off Kafka, embeds each chunk, and upserts it into
Postgres. This is the only place embedding inference happens — kept
separate from the FastAPI request path so a slow model load or a batch
re-ingestion never touches request latency.

Offsets are committed only after a successful DB write (not on message
receipt), so a worker crash mid-batch re-delivers rather than silently
dropping chunks — at-least-once, made safe by the content_hash upsert.
"""
from __future__ import annotations

import json
import logging

from confluent_kafka import Consumer
from sentence_transformers import SentenceTransformer
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.db import SessionLocal
from app.models import Chunk
from ingestion.produce import TOPIC

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker.consume")

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
GROUP_ID = "hybrid-rag-docs-worker"
BATCH_SIZE = 32


def _upsert_batch(db, model: SentenceTransformer, records: list[dict]) -> None:
    if not records:
        return
    contents = [r["content"] for r in records]
    embeddings = model.encode(contents, normalize_embeddings=True, show_progress_bar=False)

    rows = [
        {
            "source": r["source"],
            "file_path": r["file_path"],
            "url": r["url"],
            "heading_path": r["heading_path"],
            "chunk_index": r["chunk_index"],
            "content": r["content"],
            "content_hash": r["content_hash"],
            "embedding": emb.tolist(),
        }
        for r, emb in zip(records, embeddings)
    ]

    stmt = pg_insert(Chunk).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Chunk.content_hash],
        set_={
            "source": stmt.excluded.source,
            "file_path": stmt.excluded.file_path,
            "url": stmt.excluded.url,
            "heading_path": stmt.excluded.heading_path,
            "chunk_index": stmt.excluded.chunk_index,
            "content": stmt.excluded.content,
            "embedding": stmt.excluded.embedding,
        },
    )
    db.execute(stmt)
    db.commit()


def run(max_messages: int | None = None) -> int:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": GROUP_ID,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([TOPIC])

    log.info("loading embedding model %s", EMBEDDING_MODEL)
    model = SentenceTransformer(EMBEDDING_MODEL)

    processed = 0
    batch: list[dict] = []
    db = SessionLocal()
    try:
        while max_messages is None or processed < max_messages:
            msg = consumer.poll(timeout=5.0)
            if msg is None:
                if batch:
                    _upsert_batch(db, model, batch)
                    processed += len(batch)
                    log.info("upserted batch of %d (total %d)", len(batch), processed)
                    batch = []
                    consumer.commit()
                if max_messages is not None:
                    break
                continue
            if msg.error():
                log.error("kafka error: %s", msg.error())
                continue

            batch.append(json.loads(msg.value()))
            if len(batch) >= BATCH_SIZE:
                _upsert_batch(db, model, batch)
                processed += len(batch)
                log.info("upserted batch of %d (total %d)", len(batch), processed)
                batch = []
                consumer.commit()

        if batch:
            _upsert_batch(db, model, batch)
            processed += len(batch)
            consumer.commit()
    finally:
        db.close()
        consumer.close()

    log.info("done, %d chunks embedded and upserted", processed)
    return processed


if __name__ == "__main__":
    run()
