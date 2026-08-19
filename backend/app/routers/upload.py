"""Router for uploading custom documentation files, chunking, embedding,
and storing them in Postgres for immediate retrieval.
"""
from __future__ import annotations

import io
import logging
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db import get_db
from app.embeddings import get_embedding_model
from app.models import Chunk
from ingestion.chunker import chunk_text

log = logging.getLogger("app.routers.upload")

router = APIRouter(prefix="", tags=["upload"])


def _extract_text(file_bytes: bytes, filename: str) -> str:
    """Extracts plain text from uploaded markdown, text, or PDF files."""
    ext = filename.lower().split(".")[-1] if "." in filename else ""

    if ext == "pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(file_bytes))
            text_parts = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
            return "\n\n".join(text_parts)
        except ImportError:
            # If pypdf is not installed, try basic text decoding
            return file_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {e}")

    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1")


@router.post("/upload")
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    source: Annotated[str, Form()] = "upload",
    db: Session = Depends(get_db),
) -> dict:
    """Uploads a doc file (.md, .mdx, .txt, .pdf), chunks it, generates embeddings,
    and inserts it into the hybrid search database.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename missing")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    raw_text = _extract_text(contents, file.filename)
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in file")

    chunks = chunk_text(raw_text, filename=file.filename, source=source)
    if not chunks:
        raise HTTPException(status_code=400, detail="Could not extract any chunks from document")

    log.info("generating embeddings for %d chunks from %s", len(chunks), file.filename)
    model = get_embedding_model()
    embeddings = model.encode([c.content for c in chunks], normalize_embeddings=True, show_progress_bar=False)

    rows = [
        {
            "source": c.source,
            "file_path": c.file_path,
            "url": c.url,
            "heading_path": c.heading_path,
            "chunk_index": c.chunk_index,
            "content": c.content,
            "content_hash": c.content_hash,
            "embedding": emb.tolist(),
        }
        for c, emb in zip(chunks, embeddings)
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

    log.info("successfully indexed %d chunks for %s", len(chunks), file.filename)
    return {
        "filename": file.filename,
        "source": source,
        "chunks_indexed": len(chunks),
        "status": "success",
    }


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)) -> dict:
    """Returns a summary of all document sources and uploaded files in the database."""
    stmt = (
        select(
            Chunk.source,
            Chunk.file_path,
            func.count(Chunk.id).label("chunk_count"),
            func.min(Chunk.created_at).label("created_at"),
        )
        .group_by(Chunk.source, Chunk.file_path)
        .order_by(Chunk.source, Chunk.file_path)
    )
    rows = db.execute(stmt).all()

    documents = [
        {
            "source": r.source,
            "file_path": r.file_path,
            "chunk_count": r.chunk_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]

    total_chunks = sum(d["chunk_count"] for d in documents)
    return {
        "total_documents": len(documents),
        "total_chunks": total_chunks,
        "documents": documents,
    }


@router.delete("/documents/{filename:path}")
def delete_document(filename: str, db: Session = Depends(get_db)) -> dict:
    """Deletes an uploaded document and all its chunks from the database."""
    stmt = delete(Chunk).where(Chunk.file_path == filename)
    result = db.execute(stmt)
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "filename": filename,
        "chunks_deleted": result.rowcount,
        "status": "success",
    }
