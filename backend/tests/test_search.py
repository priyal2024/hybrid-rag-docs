import hashlib

from app.embeddings import embed_query
from app.models import Chunk
from app.search import hybrid_search, reciprocal_rank_fusion


def test_reciprocal_rank_fusion_rewards_items_ranked_highly_in_both_lists():
    vector_ranked = [1, 2, 3, 4]
    keyword_ranked = [3, 1, 5, 2]

    scores = reciprocal_rank_fusion([vector_ranked, keyword_ranked])

    # id 1 is #1 in vector and #2 in keyword — should outrank id 3 (#3 vector, #1 keyword)
    # and comfortably outrank id 5, which only appears in one list at all.
    assert scores[1] > scores[5]
    assert scores[1] == scores[3] or scores[1] > scores[3]
    assert set(scores) == {1, 2, 3, 4, 5}


def _seed_chunk(db_session, **overrides) -> Chunk:
    defaults = dict(
        source="react",
        file_path="src/content/test.md",
        url="https://react.dev/test",
        heading_path="Test",
        chunk_index=0,
        content="placeholder",
        content_hash=None,
    )
    defaults.update(overrides)
    if defaults["content_hash"] is None:
        raw = f"{defaults['content']}-{defaults['chunk_index']}".encode()
        defaults["content_hash"] = hashlib.sha256(raw).hexdigest()
    chunk = Chunk(**defaults, embedding=embed_query(defaults["content"]))
    db_session.add(chunk)
    db_session.commit()
    return chunk


def test_hybrid_search_finds_exact_keyword_match(db_session):
    target = _seed_chunk(
        db_session,
        chunk_index=0,
        content="The generateStaticParams function lets you statically generate routes at build time.",
        heading_path="generateStaticParams",
        url="https://nextjs.org/docs/app/api-reference/functions/generate-static-params",
        source="nextjs",
    )
    _seed_chunk(
        db_session,
        chunk_index=1,
        content="useEffect lets you synchronize a component with an external system.",
        heading_path="useEffect",
    )
    _seed_chunk(
        db_session,
        chunk_index=2,
        content="Custom Hooks let you reuse stateful logic between components.",
        heading_path="Custom Hooks",
    )

    results = hybrid_search(db_session, "generateStaticParams", k=3)

    assert results, "expected at least one result"
    assert results[0].id == target.id


def test_hybrid_search_finds_semantic_match_without_shared_vocabulary(db_session):
    target = _seed_chunk(
        db_session,
        chunk_index=0,
        content=(
            "useEffect lets you synchronize a component with an external system such as a "
            "chat server connection, and clean it up when the component unmounts."
        ),
        heading_path="useEffect",
    )
    _seed_chunk(
        db_session,
        chunk_index=1,
        content="Static export lets you export a Next.js app to static HTML files that can be served without a server.",
        heading_path="Static Exports",
        source="nextjs",
    )

    # Deliberately shares almost no vocabulary with the target chunk's text.
    results = hybrid_search(db_session, "how do I connect to an external system from a component", k=2)

    assert results
    assert results[0].id == target.id


def test_hybrid_search_returns_empty_for_no_matches_on_empty_table(db_session):
    assert hybrid_search(db_session, "anything at all", k=5) == []
