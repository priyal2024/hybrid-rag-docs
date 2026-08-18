"""CLI: fetch doc sources, chunk them, and publish each chunk to Kafka.

Ingestion is deliberately decoupled from embedding: this process only does
cheap CPU work (fetch + parse + chunk) and hands off to `worker.consume`
for the expensive part (embedding inference), via a Kafka topic. That
separation is what makes the pipeline scale independently and survive a
worker crash without re-fetching/re-chunking everything.
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict

from confluent_kafka import Producer

from app.config import settings
from ingestion.chunker import chunk_file
from ingestion.fetch_docs import list_all_doc_files, list_doc_files

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingestion.produce")

TOPIC = "doc-chunks"


def _delivery_report(err, msg) -> None:
    if err is not None:
        log.error("delivery failed for %s: %s", msg.key(), err)


def run(source: str | None, limit_per_source: int | None) -> int:
    producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})

    doc_files = (
        list_doc_files(source, limit=limit_per_source)
        if source
        else list_all_doc_files(limit_per_source=limit_per_source)
    )
    log.info("chunking %d doc files", len(doc_files))

    total_chunks = 0
    for doc_file in doc_files:
        chunks = chunk_file(doc_file.source, doc_file.path, doc_file.repo_root)
        for chunk in chunks:
            producer.produce(
                TOPIC,
                key=chunk.content_hash,
                value=json.dumps(asdict(chunk)),
                callback=_delivery_report,
            )
        total_chunks += len(chunks)
        producer.poll(0)  # trigger delivery callbacks without blocking

    producer.flush(timeout=30)
    log.info("published %d chunks from %d files to topic '%s'", total_chunks, len(doc_files), TOPIC)
    return total_chunks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["react", "nextjs"], default=None, help="limit to one source")
    parser.add_argument("--limit", type=int, default=None, help="cap files per source (for quick local runs)")
    args = parser.parse_args()
    run(args.source, args.limit)
