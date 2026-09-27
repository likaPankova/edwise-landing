from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .facts import extract_facts
from .llm_client import GPTServiceClient
from .models import (
    Fact,
    FlipCard,
    Lesson,
    LessonPlan,
    PlanSection,
    SectionKind,
)
from .themes import pick_theme


PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _lesson_corpus(lesson: Lesson) -> str:
    parts = [f"# {lesson.code}", lesson.description.strip()]
    for b in lesson.blocks:
        parts.append(f"\n## block {b.id} ({b.kind.value})")
        if b.text_plain:
            parts.append(b.text_plain)
        for c in b.flip_cards:
            parts.append(f"FLIP front: {c.front.title} — {c.front.description}")
            parts.append(f"FLIP back: {c.back.title} — {c.back.description}")
    return "\n".join(p for p in parts if p).strip()


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = re.sub(r"\s+", " ", item).strip().lower()
        if len(key) < 4 or key in seen:
            continue
        seen.add(key)
        out.append(re.sub(r"\s+", " ", item).strip())
    return out


def _extract_listish(text: str) -> list[str]:
    items: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if re.match(r"^([•\-–—*]|\d+[.)])\s+", line):
            items.append(re.sub(r"^([•\-–—*]|\d+[.)])\s+", "", line).strip())
    if items:
        return _dedupe_keep_order(items)
    # sentence chunks as soft items
    chunks = re.split(r"(?<=[.!;])\s+", text)
    return _dedupe_keep_order([c for c in chunks if 20 <= len(c) <= 180])[:12]


def build_plan_offline(lesson: Lesson, facts: list[Fact] | None = None) -> LessonPlan:
    facts = facts or extract_facts(lesson)
    corpus = _lesson_corpus(lesson)
    theme = pick_theme(corpus)

    goals: list[str] = []
    for f in facts:
        if f.category in {"description", "acceptance"} and len(goals) < 4:
            goals.append(f.text if len(f.text) < 140 else f.text[:137] + "…")
    if not goals and lesson.description:
        goals = _extract_listish(lesson.description)[:3] or [lesson.description[:160]]

    sections: list[PlanSection] = []
    sections.append(
        PlanSection(
            id="hero",
            kind=SectionKind.HERO,
            title=lesson.code,
            lead=(lesson.description.split("\n")[0][:220] if lesson.description else ""),
            fact_ids=[f.id for f in facts[:3]],
        )
    )
    sections.append(
        PlanSection(
            id="goals",
            kind=SectionKind.GOALS,
            title="Что нужно усвоить",
            items=goals[:5],
            fact_ids=[f.id for f in facts if f.category == "acceptance"][:8],
        )
    )

    # Timeline / sequence from chart or numbered lists
    timeline_items: list[str] = []
    checklist_items: list[str] = []
    warnings: list[str] = []
    definitions: list[dict[str, str]] = []
    prose_chunks: list[str] = []
    flips: list[FlipCard] = []
    media_sections: list[PlanSection] = []

    for block in lesson.blocks:
        if block.kind.value == "aiChart":
            timeline_items.extend(_extract_listish(block.chart_summary or block.text_plain)[:8])
        elif block.kind.value == "richText":
            plain = block.text_plain
            if "обязательн" in plain.lower() or re.search(r"^[•\-–]\s", plain, re.M):
                checklist_items.extend(_extract_listish(plain))
            if any(w in plain.lower() for w in ("ошибка", "нельзя", "запрет", "предупрежд", "не заменяет")):
                for s in re.split(r"(?<=[.!])\s+", plain):
                    if any(w in s.lower() for w in ("ошибка", "нельзя", "запрет", "не заменяет", "обязательно")):
                        warnings.append(s.strip())
            # definition pattern: Term — meaning
            for m in re.finditer(r"([A-ZА-ЯЁ][^.\n]{2,60})\s[—–-]\s([^.\n]{10,200})", plain):
                definitions.append({"term": m.group(1).strip(), "meaning": m.group(2).strip()})
            prose_chunks.append(plain)
        elif block.kind.value == "flipCard":
            flips.extend(block.flip_cards)
        elif block.kind.value == "aiImg":
            caption = block.text_plain or "Схема из исходного урока"
            # Prefer a concrete title from annotation / first sentence, not a generic label
            title = "Схема этапа"
            if block.img_marks:
                title = (block.img_marks[0].object or block.img_marks[0].mark_title or title).strip()
            elif caption:
                title = caption.split(".")[0][:72].strip() or title
            media_sections.append(
                PlanSection(
                    id=f"media-{block.id}",
                    kind=SectionKind.MEDIA,
                    title=title,
                    body=caption,
                    media=block.media,
                    items=[
                        m.description or m.object or ""
                        for m in block.img_marks
                        if m.description or m.object
                    ],
                    fact_ids=[],
                )
            )
        elif block.kind.value in {"rolePlay", "aiGame"}:
            sections.append(
                PlanSection(
                    id=f"practice-{block.id}",
                    kind=SectionKind.PRACTICE,
                    title="Практика",
                    body=block.text_plain,
                    fact_ids=[],
                )
            )

    if timeline_items:
        sections.append(
            PlanSection(
                id="timeline",
                kind=SectionKind.TIMELINE,
                title="Последовательность действий",
                items=_dedupe_keep_order(timeline_items)[:8],
                fact_ids=[f.id for f in facts if f.category in {"chart", "list"}][:10],
            )
        )
    if checklist_items:
        sections.append(
            PlanSection(
                id="checklist",
                kind=SectionKind.CHECKLIST,
                title="Обязательный чек-лист",
                items=_dedupe_keep_order(checklist_items)[:12],
                fact_ids=[f.id for f in facts if f.category == "list"][:12],
            )
        )
    for i, d in enumerate(definitions[:4]):
        sections.append(
            PlanSection(
                id=f"def-{i}",
                kind=SectionKind.DEFINITION,
                title=d["term"],
                body=d["meaning"],
            )
        )
    for i, w in enumerate(_dedupe_keep_order(warnings)[:3]):
        sections.append(
            PlanSection(
                id=f"warn-{i}",
                kind=SectionKind.WARNING,
                title="Критичное правило",
                body=w,
            )
        )

    # Compact prose: take unique mid-length paragraphs, avoid dumping everything
    unique_prose = _dedupe_keep_order(prose_chunks)
    if unique_prose:
        # merge into one explain section with shortened body
        body = "\n\n".join(unique_prose[:3])
        if len(body) > 1800:
            body = body[:1800].rsplit(" ", 1)[0] + "…"
        sections.append(
            PlanSection(
                id="explain",
                kind=SectionKind.PROSE,
                title="Разбор",
                body=body,
                fact_ids=[f.id for f in facts if f.category in {"rich", "description"}][:10],
            )
        )

    sections.extend(media_sections)

    if flips:
        sections.append(
            PlanSection(
                id="flip",
                kind=SectionKind.FLIP,
                title="Проверьте себя",
                pairs=[
                    {
                        "front_title": c.front.title,
                        "front_body": c.front.description,
                        "back_title": c.back.title,
                        "back_body": c.back.description,
                    }
                    for c in flips
                ],
            )
        )

    # Quiz from acceptance / checklist facts
    quiz_items: list[dict[str, Any]] = []
    for f in [x for x in facts if x.required][:5]:
        quiz_items.append(
            {
                "question": f"Верно ли: {f.text[:140]}",
                "answer": True,
                "explain": f.text,
            }
        )
    if quiz_items:
        sections.append(
            PlanSection(
                id="quiz",
                kind=SectionKind.QUIZ,
                title="Быстрая проверка",
                quiz=quiz_items,
                fact_ids=[f.id for f in facts if f.required][:5],
            )
        )

    # Summary from must-cover
    summary_items = _dedupe_keep_order(
        [f.text for f in facts if f.required][:10]
        or checklist_items[:6]
        or timeline_items[:6]
    )
    sections.append(
        PlanSection(
            id="summary",
            kind=SectionKind.SUMMARY,
            title="Итог на память",
            items=summary_items,
            fact_ids=[f.id for f in facts if f.required][:15],
        )
    )

    return LessonPlan(
        title=lesson.code,
        subtitle=theme.metaphor,
        metaphor=theme.metaphor,
        theme=theme,
        learning_goals=goals[:5],
        sections=sections,
        must_cover_fact_ids=[f.id for f in facts if f.required],
        source_lesson_ids=[lesson.id],
    )


def _media_catalog(lesson: Lesson) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for block in lesson.blocks:
        if block.kind.value != "aiImg" and not block.media:
            continue
        items: list[dict[str, Any]] = []
        for m in block.media:
            mime = (m.mimetype or "").split(";")[0].strip().lower()
            embeddable = bool(
                m.data_uri
                or (mime.startswith(("image/", "audio/", "video/")) and m.available)
            )
            if not mime and m.data_uri and m.data_uri.startswith("data:"):
                mime = m.data_uri.split(";")[0].removeprefix("data:")
                embeddable = mime.startswith(("image/", "audio/", "video/"))
            usage = "img_or_video"
            if block.kind.value == "aiGame" or mime.startswith("text/html") or mime in {
                "application/octet-stream",
                "text/plain",
            }:
                if not (mime.startswith("image/") or (m.data_uri or "").startswith("data:image/")):
                    usage = "interactive_or_html_not_for_img"
                    embeddable = False
            items.append(
                {
                    "media_id": m.media_id,
                    "placeholder": f"MEDIA:{m.media_id}",
                    "mimetype": mime or None,
                    "embeddable_as_media": embeddable,
                    "usage": usage,
                }
            )
        # Fallback ids without resolved MediaRef details
        if not items:
            for mid in block.media_ids:
                items.append(
                    {
                        "media_id": mid,
                        "placeholder": f"MEDIA:{mid}",
                        "mimetype": None,
                        "embeddable_as_media": False,
                        "usage": "unknown",
                    }
                )
        catalog.append(
            {
                "block_id": block.id,
                "kind": block.kind.value,
                "caption": (block.text_plain or "")[:400],
                "media_ids": [m.media_id for m in block.media] or list(block.media_ids),
                "media_items": items,
                "marks": [
                    {
                        "object": m.object,
                        "description": m.description,
                        "mark_title": m.mark_title,
                    }
                    for m in block.img_marks[:8]
                ],
            }
        )
    return catalog


def _block_by_id(lesson: Lesson) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for block in lesson.blocks:
        out[str(block.id)] = block
        try:
            out[str(int(block.id))] = block
        except (TypeError, ValueError):
            pass
    return out


def _parse_kind(raw: Any) -> SectionKind | None:
    if raw is None:
        return None
    key = str(raw).strip().lower()
    try:
        return SectionKind(key)
    except ValueError:
        aliases = {
            "hero_section": SectionKind.HERO,
            "goal": SectionKind.GOALS,
            "text": SectionKind.PROSE,
            "explain": SectionKind.PROSE,
            "warn": SectionKind.WARNING,
            "steps": SectionKind.TIMELINE,
            "check": SectionKind.CHECKLIST,
            "card": SectionKind.CARDS,
            "flipcard": SectionKind.FLIP,
            "test": SectionKind.QUIZ,
            "image": SectionKind.MEDIA,
            "img": SectionKind.MEDIA,
            "scheme": SectionKind.MEDIA,
            "summary_section": SectionKind.SUMMARY,
            "итог": SectionKind.SUMMARY,
        }
        return aliases.get(key)


def _as_str_list(value: Any, *, limit: int = 24) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        data = json.loads(text[start : end + 1])
        if isinstance(data, dict):
            return data
    raise ValueError("LLM answer is not a JSON object")


def _sections_from_llm(
    data: dict[str, Any],
    lesson: Lesson,
    facts: list[Fact],
) -> list[PlanSection]:
    raw_sections = data.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ValueError("LLM plan has no sections")

    blocks = _block_by_id(lesson)
    fact_ids = {f.id for f in facts}
    sections: list[PlanSection] = []
    used_ids: set[str] = set()

    for i, raw in enumerate(raw_sections):
        if not isinstance(raw, dict):
            continue
        kind = _parse_kind(raw.get("kind"))
        if kind is None:
            continue

        sid = re.sub(r"[^\w\-]+", "-", str(raw.get("id") or f"{kind.value}-{i}")).strip("-")
        if not sid:
            sid = f"{kind.value}-{i}"
        if sid in used_ids:
            sid = f"{sid}-{i}"
        used_ids.add(sid)

        media_refs = []
        media_block_ids = raw.get("media_block_ids") or raw.get("media_blocks") or []
        if not isinstance(media_block_ids, list):
            media_block_ids = []
        for bid in media_block_ids:
            block = blocks.get(str(bid))
            if block is None:
                continue
            media_refs.extend(block.media)
            if not raw.get("body") and block.text_plain:
                raw["body"] = block.text_plain
            if not raw.get("items") and block.img_marks:
                raw["items"] = [
                    m.description or m.object or ""
                    for m in block.img_marks
                    if m.description or m.object
                ]

        # If media section without ids, attach unused aiImg blocks in order
        if kind == SectionKind.MEDIA and not media_refs:
            for block in lesson.blocks:
                if block.kind.value == "aiImg" and block.media:
                    key = f"used-media-{block.id}"
                    if key in used_ids:
                        continue
                    used_ids.add(key)
                    media_refs = list(block.media)
                    if not raw.get("body"):
                        raw["body"] = block.text_plain
                    break

        pairs: list[dict[str, str]] = []
        for pair in raw.get("pairs") or []:
            if not isinstance(pair, dict):
                continue
            pairs.append(
                {
                    "front_title": str(pair.get("front_title") or ""),
                    "front_body": str(pair.get("front_body") or ""),
                    "back_title": str(pair.get("back_title") or ""),
                    "back_body": str(pair.get("back_body") or ""),
                }
            )

        quiz: list[dict[str, Any]] = []
        for q in raw.get("quiz") or []:
            if not isinstance(q, dict):
                continue
            quiz.append(
                {
                    "question": str(q.get("question") or ""),
                    "answer": bool(q.get("answer", True)),
                    "explain": str(q.get("explain") or ""),
                }
            )

        claimed = [fid for fid in _as_str_list(raw.get("fact_ids"), limit=40) if fid in fact_ids]

        title = str(raw.get("title") or kind.value).strip()
        lead = str(raw.get("lead") or "").strip()
        body = str(raw.get("body") or "").strip()
        items = _as_str_list(raw.get("items"))

        if kind == SectionKind.GOALS and not items:
            items = _as_str_list(data.get("learning_goals"), limit=6)
        if kind == SectionKind.HERO and not lead:
            lead = str(data.get("subtitle") or data.get("metaphor") or "").strip()

        sections.append(
            PlanSection(
                id=sid,
                kind=kind,
                title=title[:160],
                lead=lead[:500],
                body=body[:6000],
                items=items,
                pairs=pairs[:8],
                quiz=quiz[:8],
                media=media_refs,
                fact_ids=claimed,
            )
        )

    if len(sections) < 6:
        raise ValueError(f"LLM plan too short: {len(sections)} sections")
    if not any(s.kind == SectionKind.HERO for s in sections):
        raise ValueError("LLM plan missing hero")
    if not any(s.kind == SectionKind.SUMMARY for s in sections):
        raise ValueError("LLM plan missing summary")
    return sections


def build_plan_with_llm(
    lesson: Lesson,
    facts: list[Fact],
    client: GPTServiceClient,
) -> LessonPlan:
    """Ask model for a full structured plan; fall back to offline on failure."""
    template = _load_prompt("plan_system.txt")
    payload = {
        "lesson_title": lesson.code,
        "lesson_id": lesson.id,
        "facts": [
            {
                "id": f.id,
                "text": f.text,
                "required": f.required,
                "category": f.category,
            }
            for f in facts
        ],
        "media_catalog": _media_catalog(lesson),
        "corpus": _lesson_corpus(lesson)[:24000],
    }
    prompt = (
        template
        + "\n\nINPUT_JSON:\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n\nВерни только JSON по схеме из инструкции."
    )
    try:
        raw = client.complete(prompt, is_json=True, engine=client.default_engine)
        data = _extract_json_object(raw)
        sections = _sections_from_llm(data, lesson, facts)
        theme = pick_theme(_lesson_corpus(lesson))
        metaphor = str(data.get("metaphor") or theme.metaphor).strip() or theme.metaphor
        theme.metaphor = metaphor
        goals = _as_str_list(data.get("learning_goals"), limit=6)
        if not goals:
            for s in sections:
                if s.kind == SectionKind.GOALS and s.items:
                    goals = s.items[:6]
                    break
        if not goals:
            raise ValueError("LLM plan missing learning_goals")

        title = str(data.get("title") or lesson.code).strip() or lesson.code
        subtitle = str(data.get("subtitle") or metaphor).strip()

        # Ensure goals section items stay aligned with learning_goals
        for s in sections:
            if s.kind == SectionKind.GOALS and not s.items:
                s.items = list(goals)

        return LessonPlan(
            title=title[:200],
            subtitle=subtitle[:300],
            metaphor=metaphor[:300],
            theme=theme,
            learning_goals=goals,
            sections=sections,
            must_cover_fact_ids=[f.id for f in facts if f.required],
            source_lesson_ids=[lesson.id],
        )
    except Exception as exc:  # noqa: BLE001
        import sys

        print(f"[planner] LLM full plan failed, offline fallback: {exc}", file=sys.stderr)
        return build_plan_offline(lesson, facts)
