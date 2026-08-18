"""Fetches the doc corpus from its authoritative source: the markdown that
powers react.dev and nextjs.org, pulled directly from their own repos rather
than scraped off the rendered site (faster, and avoids fighting client-side
rendering / robots rules).

Uses a blobless, sparse-checkout clone so only the docs subdirectory is
actually downloaded, not each repo's full history or unrelated source tree.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

SOURCES = {
    "react": {
        "repo": "https://github.com/reactjs/react.dev.git",
        "sparse_path": "src/content",
        "content_root": "src/content",
        "glob": "*.md",
    },
    "nextjs": {
        "repo": "https://github.com/vercel/next.js.git",
        "sparse_path": "docs",
        "content_root": "docs",
        "glob": "*.mdx",
    },
}


@dataclass(frozen=True)
class DocFile:
    source: str
    path: Path       # absolute path on disk
    repo_root: Path  # absolute path to the source's checked-out repo root


def _sparse_clone(source: str, cfg: dict, dest: Path) -> None:
    subprocess.run(
        [
            "git", "clone",
            "--filter=blob:none", "--no-checkout", "--depth", "1",
            cfg["repo"], str(dest),
        ],
        check=True,
    )
    subprocess.run(["git", "sparse-checkout", "init", "--cone"], cwd=dest, check=True)
    subprocess.run(["git", "sparse-checkout", "set", cfg["sparse_path"]], cwd=dest, check=True)
    subprocess.run(["git", "checkout"], cwd=dest, check=True)


def fetch(source: str, refresh: bool = False) -> Path:
    """Ensures the given source's docs are checked out locally, returns the repo root."""
    cfg = SOURCES[source]
    dest = DATA_DIR / source
    if refresh and dest.exists():
        subprocess.run(["git", "pull", "--depth", "1"], cwd=dest, check=True)
    elif not dest.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _sparse_clone(source, cfg, dest)
    return dest


def list_doc_files(source: str, limit: int | None = None) -> list[DocFile]:
    """Lists content files for a source, fetching it first if not already present."""
    cfg = SOURCES[source]
    repo_root = fetch(source)
    content_root = repo_root / cfg["content_root"]
    files = sorted(content_root.rglob(cfg["glob"]))
    if limit is not None:
        files = files[:limit]
    return [DocFile(source=source, path=f, repo_root=repo_root) for f in files]


def list_all_doc_files(limit_per_source: int | None = None) -> list[DocFile]:
    result: list[DocFile] = []
    for source in SOURCES:
        result.extend(list_doc_files(source, limit=limit_per_source))
    return result
