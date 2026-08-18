from app.generate import build_prompt
from app.search import SearchResult


def _result(i: int) -> SearchResult:
    return SearchResult(
        id=i,
        source="react",
        url=f"https://react.dev/doc-{i}",
        heading_path=f"Heading {i}",
        content=f"Content body {i}.",
        score=1.0 / i,
    )


def test_build_prompt_numbers_snippets_matching_citation_convention():
    results = [_result(1), _result(2)]
    system_prompt, user_prompt = build_prompt("How does X work?", results)

    assert "How does X work?" in user_prompt
    assert "[1] (Heading 1)" in user_prompt
    assert "[2] (Heading 2)" in user_prompt
    assert "Content body 1." in user_prompt
    assert "Content body 2." in user_prompt
    assert "cite" in system_prompt.lower()


def test_build_prompt_handles_single_result():
    system_prompt, user_prompt = build_prompt("query", [_result(1)])
    assert "[1]" in user_prompt
    assert "[2]" not in user_prompt
