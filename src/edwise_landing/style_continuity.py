from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def course_style_id(course_path: Path | str) -> str:
    """Stable id for a course JSON file (stem, e.g. 4763)."""
    return Path(course_path).stem


def default_course_style_path(
    course_path: Path | str,
    *,
    out_dir: Path | str = "outputs",
) -> Path:
    """outputs/course_styles/<course_id>_style.json"""
    return Path(out_dir) / "course_styles" / f"{course_style_id(course_path)}_style.json"


def extract_style_continuity(prev_html: str | Path, *, max_chars: int = 9000) -> dict[str, Any]:
    """
    Compact fingerprint of lesson HTML so later lessons in the same course
    can match palette, layout patterns, and narrative voice.
    """
    if isinstance(prev_html, Path) or (
        isinstance(prev_html, str) and ("<" not in prev_html[:200] and Path(prev_html).exists())
    ):
        text = Path(prev_html).read_text(encoding="utf-8", errors="replace")
    else:
        text = str(prev_html)

    # Strip embedded media noise before extracting CSS samples
    css_source = re.sub(
        r"url\(\s*(['\"]?)(?:data:|https?:)[^)]+?\1\s*\)",
        "url(HERO_OR_MEDIA)",
        text,
        flags=re.I,
    )

    root_m = re.search(r":root\s*\{([^}]+)\}", css_source, re.I | re.S)
    css_root = ""
    if root_m:
        css_root = ":root{" + re.sub(r"\s+", " ", root_m.group(1)).strip() + "}"

    css_skeleton: dict[str, str] = {}
    for sel in (
        ".hero",
        ".hero-inner",
        ".lead",
        "h1",
        "h2",
        ".eyebrow",
        ".goal-card",
        ".goals-grid",
        ".edw-steps",
        ".edw-warning",
        ".edw-checklist",
        ".edw-key-takeaway",
        ".progress-bar",
        ".progress-track",
        ".quiz-item",
        ".flip-wrap",
        ".flip-card",
        ".flip-hint",
        ".media-figure",
        ".mini-nav",
        ".container",
        "body",
    ):
        m = re.search(re.escape(sel) + r"\s*\{([^}]+)\}", css_source)
        if m:
            css_skeleton[sel] = re.sub(r"\s+", " ", m.group(1)).strip()[:320]

    h1s = [_strip_tags(x) for x in re.findall(r"<h1[^>]*>(.*?)</h1>", text, re.I | re.S)]
    h2s = [_strip_tags(x) for x in re.findall(r"<h2[^>]*>(.*?)</h2>", text, re.I | re.S)]

    class_names: set[str] = set()
    for attr in re.findall(r'class="([^"]+)"', text):
        for part in attr.split():
            if part.startswith("edw-") or part in {
                "hero",
                "eyebrow",
                "lead",
                "goals-grid",
                "goal-card",
                "progress-bar",
                "flip-wrap",
                "flip-card",
                "flip-hint",
                "quiz-item",
                "media-figure",
                "mini-nav",
                "container",
                "reveal",
            }:
                class_names.add(part)

    paras = [_strip_tags(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", text, re.I | re.S)]
    narrative = [p for p in paras if len(p) >= 50][:6]

    structure_hits = re.findall(
        r'class="[^"]*\b(hero|goals-grid|edw-steps|edw-checklist|edw-warning|'
        r'flip-wrap|flip-card|quiz-item|edw-key-takeaway|media-figure|mini-nav)\b',
        text,
    )
    structure_order: list[str] = []
    for name in structure_hits:
        if not structure_order or structure_order[-1] != name:
            structure_order.append(name)

    fingerprint = {
        "purpose": (
            "Это эталон стиля курса (course style lock). "
            "Новый урок должен выглядеть и читаться как часть того же курса: "
            "та же палитра/типографика, те же паттерны секций и анимаций, "
            "тот же деловой тон повествования. Не копируй текст и медиа — "
            "копируй только стилистику оформления и голос."
        ),
        "css_root": css_root[:1500],
        "css_skeleton": css_skeleton,
        "previous_title": h1s[0] if h1s else "",
        "section_heading_examples": h2s[:12],
        "layout_classes": sorted(class_names)[:60],
        "structure_order": structure_order[:24],
        "narrative_voice_samples": narrative,
        "continuity_rules": [
            "Те же CSS variables и имена (--edw-*), без новой палитры под тему урока.",
            "Перенеси css_skeleton почти дословно (селекторы, размеры, отступы, hover). "
            "Допускается менять только контент и медиа, не изобретай новую систему компонентов.",
            "Hero как в эталоне: тёмный фон + HERO_BG (если есть) + градиентный overlay primary/secondary, "
            "белый H1, светлый lead, floating shapes; текст снизу (align-items:flex-end).",
            "Те же секции и ритм: цели → объяснение → шаги → медиа → практика → quiz/flip → итог.",
            "Те же wow-эффекты: progress bar, scroll reveal, hover-lift, steps highlight.",
            "Тон: краткие деловые предложения, обращение к оператору («вы»), без ИИ-штампов.",
            "Заголовки секций в том же регистре и длине, что в section_heading_examples.",
            "Компоненты edw-* и quiz/flip разметка как в эталоне курса.",
            "Имена классов progress-bar / progress-track / goal-card / flip-* сохраняй как в эталоне.",
            "Flip-карточки всегда внутри .flip-wrap с justify-content:center (по центру контейнера), "
            "не прижимай карточку к левому краю; подсказка .flip-hint — text-align:center под карточкой.",
        ],
    }

    raw = str(fingerprint)
    if len(raw) > max_chars:
        fingerprint["narrative_voice_samples"] = narrative[:3]
        fingerprint["section_heading_examples"] = h2s[:8]
    return fingerprint


def load_style_continuity(path: Path | str | None) -> dict[str, Any] | None:
    """Load fingerprint from previous HTML or from a saved course_style JSON."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"style continuity source not found: {p}")
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"course style JSON must be an object: {p}")
        if "css_root" in data or "css_skeleton" in data:
            return data
        inner = data.get("style_continuity")
        if isinstance(inner, dict):
            return inner
        raise ValueError(f"unrecognized course style JSON shape: {p}")
    return extract_style_continuity(p)


def save_course_style(
    path: Path | str,
    *,
    fingerprint: dict[str, Any] | None = None,
    html: str | Path | None = None,
    course_id: str | None = None,
    source_lesson_ids: list[int] | None = None,
    source_html: str | None = None,
) -> Path:
    """Persist course style lock JSON. Prefer fingerprint, else extract from html."""
    if fingerprint is None:
        if html is None:
            raise ValueError("save_course_style requires fingerprint or html")
        fingerprint = extract_style_continuity(html)

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "course_id": course_id or out.stem.replace("_style", ""),
        "source_lesson_ids": source_lesson_ids or [],
        "source_html": source_html,
        "style_continuity": fingerprint,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def resolve_course_style_for_run(
    course_path: Path | str,
    *,
    out_dir: Path | str = "outputs",
    course_style_path: Path | str | None = None,
    prev_html_path: Path | str | None = None,
    relock: bool = False,
) -> tuple[dict[str, Any] | None, Path, str]:
    """
    Resolve style continuity for a pipeline run.

    Returns (fingerprint_or_None, lock_path, source_tag).
    source_tag: "course_style" | "prev_html" | "none"
    """
    lock_path = (
        Path(course_style_path)
        if course_style_path
        else default_course_style_path(course_path, out_dir=out_dir)
    )

    if not relock and lock_path.exists():
        return load_style_continuity(lock_path), lock_path, "course_style"

    if prev_html_path:
        return load_style_continuity(prev_html_path), lock_path, "prev_html"

    return None, lock_path, "none"
