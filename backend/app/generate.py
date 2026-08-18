"""Turns retrieved chunks + a question into a streamed, cited answer.

Uses the plain OpenAI Python client pointed at Groq's OpenAI-compatible
endpoint (see `app.config.settings.llm_base_url`) rather than a framework
like LangChain for this one call — there's nothing here a chain buys you
over a single prompt + streaming loop, and it keeps the provider swap
(Groq -> real OpenAI) to a one-line base_url/key change with no code churn.
"""
from __future__ import annotations

from collections.abc import Iterator

from openai import OpenAI

from app.config import settings
from app.search import SearchResult

SYSTEM_PROMPT = (
    "You are a documentation assistant for React and Next.js. Answer the "
    "question using ONLY the numbered context snippets below — do not use "
    "outside knowledge. Cite the snippets you rely on inline like [1] or [2], "
    "matching their numbers. If the snippets don't contain enough to answer, "
    "say so plainly instead of guessing."
)


def _get_client() -> OpenAI:
    return OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


def build_prompt(query: str, results: list[SearchResult]) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt). Pure and side-effect-free —
    the part of this module worth unit testing without a live LLM call."""
    context = "\n\n---\n\n".join(
        f"[{i + 1}] ({r.heading_path})\n{r.content}" for i, r in enumerate(results)
    )
    user_prompt = f"Context:\n{context}\n\nQuestion: {query}"
    return SYSTEM_PROMPT, user_prompt


def generate_answer(query: str, results: list[SearchResult]) -> Iterator[str]:
    """Yields answer text incrementally. Caller is expected to have already
    checked `results` is non-empty — this makes no judgment call about
    what to say when there's no context to answer from."""
    system_prompt, user_prompt = build_prompt(query, results)
    client = _get_client()
    stream = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
