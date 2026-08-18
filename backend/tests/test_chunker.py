from pathlib import Path

from ingestion.chunker import build_url, chunk_file

FIXTURE_MD = """---
title: useThing
---

<Intro>

`useThing` is a hook.

</Intro>

Some intro text before any heading.

## Reference {/*reference*/}

### `useThing(value)` {/*usething*/}

Call `useThing` at the top level.

## Usage

Here is how you use it in practice, at some length so we can exercise the
paragraph-splitting behaviour for over-long sections.

""" + ("This paragraph repeats to pad length out. " * 60) + """

Final paragraph after the padding.
"""


def test_build_url_react():
    assert build_url("react", Path("src/content/reference/react/useEffect.md")) == (
        "https://react.dev/reference/react/useEffect"
    )


def test_build_url_react_index():
    assert build_url("react", Path("src/content/blog/index.md")) == "https://react.dev/blog"


def test_build_url_nextjs_strips_numeric_prefixes():
    assert build_url(
        "nextjs", Path("docs/01-app/02-guides/09-self-hosting.mdx")
    ) == "https://nextjs.org/docs/app/guides/self-hosting"


def test_chunk_file_splits_on_headings_and_strips_jsx(tmp_path):
    repo_root = tmp_path
    content_dir = repo_root / "src" / "content" / "reference" / "react"
    content_dir.mkdir(parents=True)
    doc_path = content_dir / "useThing.md"
    doc_path.write_text(FIXTURE_MD, encoding="utf-8")

    chunks = chunk_file("react", doc_path, repo_root)

    assert len(chunks) >= 3
    assert all(c.source == "react" for c in chunks)
    assert all(c.url == "https://react.dev/reference/react/useThing" for c in chunks)

    # JSX component tags should not leak into chunk content
    assert not any("<Intro>" in c.content for c in chunks)

    # heading hierarchy is preserved
    heading_paths = [c.heading_path for c in chunks]
    assert any("Reference" in hp for hp in heading_paths)
    assert any("useThing(value)" in hp for hp in heading_paths)

    # react.dev's `{/*anchor*/}` heading annotations are stripped
    assert not any("{/*" in hp for hp in heading_paths)


def test_chunk_file_splits_long_sections_by_paragraph(tmp_path):
    repo_root = tmp_path
    content_dir = repo_root / "src" / "content" / "learn"
    content_dir.mkdir(parents=True)
    doc_path = content_dir / "long.md"
    doc_path.write_text(FIXTURE_MD, encoding="utf-8")

    chunks = chunk_file("react", doc_path, repo_root)
    usage_chunks = [c for c in chunks if "Usage" in c.heading_path]

    assert len(usage_chunks) >= 2
    assert all(len(c.content) <= 2100 for c in chunks)  # heading prefix adds a little slack


def test_chunk_file_is_deterministic_and_hashes_differ(tmp_path):
    repo_root = tmp_path
    content_dir = repo_root / "src" / "content" / "learn"
    content_dir.mkdir(parents=True)
    doc_path = content_dir / "useThing.md"
    doc_path.write_text(FIXTURE_MD, encoding="utf-8")

    chunks_a = chunk_file("react", doc_path, repo_root)
    chunks_b = chunk_file("react", doc_path, repo_root)

    assert [c.content_hash for c in chunks_a] == [c.content_hash for c in chunks_b]
    assert len({c.content_hash for c in chunks_a}) == len(chunks_a)
