"""Turns a raw doc file into retrieval-sized chunks.

Deliberately heading-aware rather than a fixed-size sliding window: splitting
on ## / ### boundaries keeps each chunk topically coherent (e.g. the whole
"Parameters" section of a hook's reference page stays together), which is
what actually makes hybrid retrieval precise instead of returning half of one
idea and half of another.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

MAX_CHUNK_CHARS = 2000
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n|\n(?=[-*]\s|\d+\.\s)")

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_FRONTMATTER_TITLE_RE = re.compile(r"^title:\s*(.+)$", re.MULTILINE)
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.MULTILINE)
_HEADING_ANCHOR_RE = re.compile(r"\s*\{/\*.*?\*/\}\s*$")  # react.dev's `## Title {/*slug*/}`
_JSX_LINE_RE = re.compile(r"^\s*</?[A-Z][A-Za-z.]*(\s[^>]*)?/?>\s*$", re.MULTILINE)
_NUMERIC_PREFIX_RE = re.compile(r"^\d+-")


@dataclass(frozen=True)
class Chunk:
    source: str
    file_path: str      # relative path, for traceability back to the repo
    url: str
    heading_path: str    # e.g. "useEffect > Reference > useEffect(setup, dependencies?)"
    chunk_index: int
    content: str
    content_hash: str


def _strip_frontmatter(text: str) -> tuple[str, str | None]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return text, None
    frontmatter = match.group(1)
    title_match = _FRONTMATTER_TITLE_RE.search(frontmatter)
    title = title_match.group(1).strip().strip('"').strip("'") if title_match else None
    return text[match.end():], title


def _clean_body(text: str) -> str:
    text = _JSX_LINE_RE.sub("", text)
    return text


def _clean_heading(raw: str) -> str:
    raw = _HEADING_ANCHOR_RE.sub("", raw)
    return raw.strip(" `")


def _hard_wrap(text: str, max_chars: int) -> list[str]:
    """Last-resort split on word boundaries, for a single paragraph that alone
    exceeds max_chars (no blank line inside it for the paragraph split to use)."""
    words = text.split(" ")
    parts: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}" if current else word
        if len(candidate) > max_chars and current:
            parts.append(current)
            current = word
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def _split_by_paragraph(text: str, max_chars: int) -> list[str]:
    """Sub-splits an over-long section on paragraph boundaries, never mid-sentence
    where avoidable; falls back to word-boundary wrapping for a single paragraph
    that alone exceeds the limit."""
    if len(text) <= max_chars:
        return [text]
    paragraphs = _PARAGRAPH_SPLIT_RE.split(text)
    parts: list[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > max_chars:
            if current.strip():
                parts.append(current.strip())
                current = ""
            parts.extend(_hard_wrap(para, max_chars))
            continue
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > max_chars and current:
            parts.append(current.strip())
            current = para
        else:
            current = candidate
    if current.strip():
        parts.append(current.strip())
    return parts or [text]


def build_url(source: str, repo_relative_path: Path) -> str:
    parts = list(repo_relative_path.with_suffix("").parts)
    if source == "react":
        # src/content/reference/react/useEffect.md -> react.dev/reference/react/useEffect
        parts = parts[2:]  # drop "src", "content"
        base = "https://react.dev"
    elif source == "nextjs":
        # docs/01-app/02-guides/09-self-hosting.mdx -> nextjs.org/docs/app/guides/self-hosting
        parts = [_NUMERIC_PREFIX_RE.sub("", p) for p in parts]
        base = "https://nextjs.org"
    else:
        raise ValueError(f"unknown source: {source}")

    if parts and parts[-1] == "index":
        parts = parts[:-1]
    return "/".join([base, *parts])


def chunk_file(source: str, absolute_path: Path, repo_root: Path) -> list[Chunk]:
    """repo_root is the source's checked-out repo root (e.g. data/raw/react),
    used to compute the repo-relative path for both the URL and traceability."""
    raw = absolute_path.read_text(encoding="utf-8")
    body, title = _strip_frontmatter(raw)
    body = _clean_body(body)

    relative_path = absolute_path.relative_to(repo_root)
    url = build_url(source, relative_path)

    # Split on h2/h3 headings; text before the first heading becomes its own
    # section under just the page title.
    headings = list(_HEADING_RE.finditer(body))
    sections: list[tuple[str, str]] = []  # (heading_path, section_text)
    top_path = title or absolute_path.stem

    if not headings:
        sections.append((top_path, body))
    else:
        first_start = headings[0].start()
        intro = body[:first_start].strip()
        if intro:
            sections.append((top_path, intro))
        current_h2: str | None = None
        for i, h in enumerate(headings):
            level = len(h.group(1))
            heading_text = _clean_heading(h.group(2))
            start = h.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
            section_text = body[start:end].strip()

            if level == 2:
                current_h2 = heading_text
                heading_path = f"{top_path} > {heading_text}"
            else:  # level == 3, nested under the most recent h2 (if any)
                heading_path = (
                    f"{top_path} > {current_h2} > {heading_text}"
                    if current_h2
                    else f"{top_path} > {heading_text}"
                )
            sections.append((heading_path, section_text))

    chunks: list[Chunk] = []
    idx = 0
    for heading_path, text in sections:
        text = text.strip()
        if not text:
            continue
        for part in _split_by_paragraph(text, MAX_CHUNK_CHARS):
            if not part.strip():
                continue
            content = f"{heading_path}\n\n{part}"
            content_hash = hashlib.sha256(f"{source}:{relative_path}:{idx}:{content}".encode()).hexdigest()
            chunks.append(
                Chunk(
                    source=source,
                    file_path=str(relative_path),
                    url=url,
                    heading_path=heading_path,
                    chunk_index=idx,
                    content=content,
                    content_hash=content_hash,
                )
            )
            idx += 1
    return chunks


def chunk_text(raw_text: str, filename: str, source: str = "upload", base_url: str | None = None) -> list[Chunk]:
    """Chunks in-memory text from user uploads or arbitrary sources."""
    body, title = _strip_frontmatter(raw_text)
    body = _clean_body(body)

    stem = Path(filename).stem
    top_path = title or stem
    url = base_url or f"#upload/{filename}"

    headings = list(_HEADING_RE.finditer(body))
    sections: list[tuple[str, str]] = []

    if not headings:
        sections.append((top_path, body))
    else:
        first_start = headings[0].start()
        intro = body[:first_start].strip()
        if intro:
            sections.append((top_path, intro))
        current_h2: str | None = None
        for i, h in enumerate(headings):
            level = len(h.group(1))
            heading_text = _clean_heading(h.group(2))
            start = h.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
            section_text = body[start:end].strip()

            if level == 2:
                current_h2 = heading_text
                heading_path = f"{top_path} > {heading_text}"
            else:
                heading_path = (
                    f"{top_path} > {current_h2} > {heading_text}"
                    if current_h2
                    else f"{top_path} > {heading_text}"
                )
            sections.append((heading_path, section_text))

    chunks: list[Chunk] = []
    idx = 0
    for heading_path, text in sections:
        text = text.strip()
        if not text:
            continue
        for part in _split_by_paragraph(text, MAX_CHUNK_CHARS):
            if not part.strip():
                continue
            content = f"{heading_path}\n\n{part}"
            content_hash = hashlib.sha256(f"{source}:{filename}:{idx}:{content}".encode()).hexdigest()
            chunks.append(
                Chunk(
                    source=source,
                    file_path=filename,
                    url=url,
                    heading_path=heading_path,
                    chunk_index=idx,
                    content=content,
                    content_hash=content_hash,
                )
            )
            idx += 1
    return chunks

