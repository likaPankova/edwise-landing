from __future__ import annotations

import json
from typing import Any

from .genmedia_client import GenMediaClient, GenMediaImageResult
from .llm_client import GPTServiceClient
from .models import Fact, Lesson
from .planner import _lesson_corpus, _load_prompt


def _pick_context_facts(facts: list[Fact], limit: int = 12) -> list[str]:
    out: list[str] = []
    for f in facts:
        if f.required or f.category in {"acceptance", "description", "list"}:
            out.append(f.text[:220])
        if len(out) >= limit:
            break
    if not out:
        out = [f.text[:220] for f in facts[:8]]
    return out


def build_hero_image_prompt(
    lesson: Lesson,
    facts: list[Fact],
    client: GPTServiceClient,
    *,
    brand_summary: str = "",
) -> str:
    """Ask LLM for a domain-relevant hero image prompt."""
    template = _load_prompt("hero_image_prompt.txt")
    payload: dict[str, Any] = {
        "lesson_title": lesson.code,
        "lesson_description": (lesson.description or "")[:1200],
        "key_facts": _pick_context_facts(facts),
        "topic_corpus_excerpt": _lesson_corpus(lesson)[:4000],
        "brand_summary": brand_summary,
    }
    prompt = (
        template
        + "\n\nINPUT_JSON:\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\nВерни только текст промпта."
    )
    # Prefer luna for short prompt drafting when the default engine is Claude.
    engine = "gpt-5.6-luna" if client.default_engine == "claude-sonnet-5" else client.default_engine
    raw = client.complete(prompt, is_json=False, engine=engine, asynchronous=False)
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        raise ValueError("Empty hero image prompt from LLM")
    return text[:2000]


def generate_lesson_hero_image(
    lesson: Lesson,
    facts: list[Fact],
    gpt_client: GPTServiceClient,
    genmedia: GenMediaClient,
    *,
    brand_summary: str = "",
) -> GenMediaImageResult:
    image_prompt = build_hero_image_prompt(lesson, facts, gpt_client, brand_summary=brand_summary)
    return genmedia.generate_image(image_prompt, orientation="landscape")
