from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .component_catalog import catalog_for_prompt, load_course_base_css
from .genmedia_client import GenMediaClient
from .hero_image import generate_lesson_hero_image
from .llm_client import GPTServiceClient
from .models import Fact, Lesson
from .planner import _lesson_corpus, _load_prompt, _media_catalog
from .style_continuity import load_style_continuity
from .style_tokens import load_brand_style


def _extract_html(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:html|HTML)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.lower().find("<!doctype html")
    if start < 0:
        start = text.lower().find("<html")
    if start >= 0:
        text = text[start:]
    end = text.lower().rfind("</html>")
    if end >= 0:
        text = text[: end + len("</html>")]
    text = text.strip()
    if not text.lower().startswith("<!doctype html") and text.lower().startswith("<html"):
        text = "<!DOCTYPE html>\n" + text
    if "<html" not in text.lower():
        raise ValueError("LLM answer is not an HTML document")
    return text


def _media_src_map(lesson: Lesson) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for block in lesson.blocks:
        for m in block.media:
            src = m.data_uri or m.resolved_url or m.s3_url
            if not src:
                continue
            mapping[str(m.media_id)] = src
    return mapping


def _apply_media_placeholders(html: str, lesson: Lesson, *, hero_src: str | None = None) -> str:
    mapping = _media_src_map(lesson)

    def repl(match: re.Match[str]) -> str:
        mid = match.group(1)
        return mapping.get(mid, match.group(0))

    # MEDIA:123 inside src="..." or bare
    html = re.sub(r"MEDIA:(\d+)", repl, html)
    if hero_src:
        html = html.replace("HERO_BG", hero_src)
    return html


def apply_course_css_template(html: str, *, hero_src: str | None = None) -> str:
    """Replace page <style> with shared course_base.css (+ hero image var)."""
    # Align common LLM JS class names with the shared CSS contract.
    html = re.sub(
        r"classList\.add\(['\"](?:is-visible|visible|reached)['\"]\)",
        "classList.add('in-view')",
        html,
    )
    html = re.sub(
        r"classList\.toggle\(['\"]is-flipped['\"]\)",
        "classList.toggle('flipped')",
        html,
    )
    base = load_course_base_css()
    extras: list[str] = []
    if hero_src:
        safe = hero_src.replace("'", "%27")
        extras.append(f".hero{{--edw-hero-image:url('{safe}');}}")
        extras.append(
            ".hero{"
            "background-image:"
            "linear-gradient(135deg, rgba(236,138,0,.55), rgba(129,150,161,.55)),"
            "linear-gradient(0deg, rgba(15,20,24,.72), rgba(15,20,24,.28)),"
            f"url('{safe}');"
            "background-size:cover;background-position:center;}"
        )
    style_inner = base + ("\n" + "\n".join(extras) if extras else "")
    style_block = f"<style>\n{style_inner}\n</style>"
    if re.search(r"<style\b[^>]*>.*?</style>", html, flags=re.I | re.S):
        return re.sub(
            r"<style\b[^>]*>.*?</style>",
            style_block,
            html,
            count=1,
            flags=re.I | re.S,
        )
    if re.search(r"</head>", html, flags=re.I):
        return re.sub(r"</head>", style_block + "\n</head>", html, count=1, flags=re.I)
    return style_block + "\n" + html


def build_html_with_llm(
    lesson: Lesson,
    facts: list[Fact],
    client: GPTServiceClient,
    *,
    project_root: Path | None = None,
    style_path: Path | str | None = None,
    prev_html_path: Path | str | None = None,
    style_continuity: dict[str, Any] | None = None,
    generate_hero: bool = True,
    use_css_template: bool = False,
) -> tuple[str, list[str]]:
    """Build a standalone HTML page via LLM.

    use_css_template: if True, replace generated <style> with course_base.css.
    Default False — prefer model CSS plus course_style continuity.
    """
    extra_warnings: list[str] = []
    template = _load_prompt("full_html_system.txt")
    catalog = []
    for item in _media_catalog(lesson):
        entry = dict(item)
        # expose placeholder ids for each media file
        placeholders = []
        for mid in entry.get("media_ids") or []:
            placeholders.append(f"MEDIA:{mid}")
        entry["src_placeholders"] = placeholders
        catalog.append(entry)

    brand_style = load_brand_style(style_path, project_root=project_root)
    continuity = style_continuity
    if continuity is None and prev_html_path:
        try:
            continuity = load_style_continuity(prev_html_path)
        except Exception as exc:  # noqa: BLE001
            extra_warnings.append(f"style_continuity_failed:{exc}")

    try:
        component_catalog = catalog_for_prompt(compact=True)
    except Exception as exc:  # noqa: BLE001
        component_catalog = None
        extra_warnings.append(f"component_catalog_failed:{exc}")

    hero_image: dict[str, Any] | None = None
    hero_src: str | None = None
    if generate_hero:
        genmedia = GenMediaClient.from_env()
        if genmedia:
            try:
                hero = generate_lesson_hero_image(
                    lesson,
                    facts,
                    client,
                    genmedia,
                    brand_summary=str(brand_style.get("style_summary") or ""),
                )
                hero_src = hero.data_uri or hero.raw_preview_url
                hero_image = {
                    "placeholder": "HERO_BG",
                    "prompt": hero.prompt,
                    "task_id": hero.task_id,
                    "engine": hero.engine,
                    "embedded": bool(hero.data_uri),
                    "usage_hint": (
                        "Используй HERO_BG как фон hero-секции или широкий баннер в начале "
                        "(background-image / <img>), с overlay для читаемости текста."
                    ),
                }
            except Exception as exc:  # noqa: BLE001
                extra_warnings.append(f"genmedia_hero_failed:{exc}")
        else:
            extra_warnings.append("genmedia:not_configured")

    payload = {
        "lesson_title": lesson.code,
        "lesson_id": lesson.id,
        "brand_style": brand_style,
        "component_catalog": component_catalog,
        "style_continuity": continuity,
        "css_template_mode": use_css_template,
        "hero_image": hero_image,
        "facts": [
            {
                "id": f.id,
                "text": f.text,
                "required": f.required,
                "category": f.category,
            }
            for f in facts
        ],
        "media_catalog": catalog,
        "corpus": _lesson_corpus(lesson)[:22000],
    }
    prompt = (
        template
        + "\n\nINPUT_JSON:\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\nВерни только полный HTML-документ."
    )
    # Long HTML: prefer async on gateway; keep is_json=false for non-JSON engines.
    raw = client.complete(
        prompt,
        is_json=False,
        engine=client.default_engine,
        asynchronous=True,
    )
    html = _extract_html(raw)
    html = _apply_media_placeholders(html, lesson, hero_src=hero_src)
    if use_css_template:
        try:
            html = apply_course_css_template(html, hero_src=hero_src)
            extra_warnings.append("css_template:applied")
        except Exception as exc:  # noqa: BLE001
            extra_warnings.append(f"css_template_failed:{exc}")
    return html, extra_warnings
