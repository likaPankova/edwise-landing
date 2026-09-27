from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from typing import Any
from bs4 import BeautifulSoup

from .models import (
    BlockKind,
    FlipCard,
    FlipSide,
    ImgMark,
    Lesson,
    LessonBlock,
    MediaRef,
)


KIND_MAP = {
    "richtext": BlockKind.RICH_TEXT,
    "aiimg": BlockKind.AI_IMG,
    "aichart": BlockKind.AI_CHART,
    "flipcard": BlockKind.FLIP_CARD,
    "aigame": BlockKind.AI_GAME,
    "roleplay": BlockKind.ROLE_PLAY,
}


def load_course(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "data" in data:
        return list(data["data"])
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported course JSON shape in {path}")


def select_lessons(
    steps: list[dict[str, Any]],
    lesson_ids: list[int],
    *,
    allow_tests: bool = False,
) -> list[dict[str, Any]]:
    by_id = {int(s["id"]): s for s in steps}
    missing = [i for i in lesson_ids if i not in by_id]
    if missing:
        raise KeyError(f"Lesson ids not found: {missing}")
    selected = [by_id[i] for i in lesson_ids]
    if not allow_tests:
        selected = [
            s
            for s in selected
            if not (s.get("scheme_description") or {}).get("isTest")
        ]
    if not selected:
        raise ValueError("No non-test lessons selected")
    return selected


def html_to_plain(html: str | None) -> str:
    if not html or html.strip() in {"null", "None"}:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sanitize_html_fragment(html: str | None) -> str:
    """Keep readable markup; strip scripts/styles/event handlers."""
    if not html or html.strip() in {"null", "None"}:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "iframe", "object", "embed"]):
        tag.decompose()
    for tag in soup.find_all(True):
        attrs = dict(tag.attrs)
        for attr, value in attrs.items():
            if attr.lower().startswith("on"):
                del tag.attrs[attr]
            elif attr.lower() in {"href", "src", "xlink:href"} and isinstance(value, str):
                if value.strip().lower().startswith(("javascript:", "data:text/html")):
                    del tag.attrs[attr]
        # Drop noisy inline style noise from Edwise widgets for landing reuse
        if "style" in tag.attrs and tag.name not in {"span", "mark"}:
            # keep border-left cues for warnings via class only
            del tag.attrs["style"]
    body = soup.body
    root = body if body else soup
    # unwrap fake <root> wrappers seen in exports
    for fake in root.find_all("root"):
        fake.unwrap()
    return "".join(str(c) for c in root.contents).strip()


def _parse_jsonish(raw: str | None) -> Any | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text or text in {"null", "None", "undefined"}:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _build_media_index(step: dict[str, Any]) -> dict[int, MediaRef]:
    index: dict[int, MediaRef] = {}
    for item in step.get("media") or []:
        info = item.get("file_info") if isinstance(item, dict) else None
        if not isinstance(info, dict):
            info = item if isinstance(item, dict) else {}
        mid = info.get("id")
        if mid is None:
            continue
        mid = int(mid)
        index[mid] = MediaRef(
            media_id=mid,
            name=info.get("original_name") or info.get("name") or info.get("file_name"),
            mimetype=info.get("mimetype"),
            s3_url=info.get("s3_url"),
            resolved_url=info.get("s3_url"),
            available=bool(info.get("s3_url")),
        )
    return index


def _normalize_block(attr: dict[str, Any], media_index: dict[int, MediaRef]) -> LessonBlock:
    warnings: list[str] = []
    raw_name = attr.get("name")
    if raw_name is None or str(raw_name).strip() == "":
        warnings.append("missing_block_name")
        kind = BlockKind.UNKNOWN
    else:
        key = re.sub(r"[^a-zA-Z]", "", str(raw_name)).lower()
        kind = KIND_MAP.get(key, BlockKind.UNKNOWN)
        if kind is BlockKind.UNKNOWN:
            warnings.append(f"unknown_block_name:{raw_name}")

    raw_text = attr.get("text")
    if isinstance(raw_text, str) and raw_text.strip() == "null":
        warnings.append("text_literal_null")
        raw_text = None

    media_ids = [int(x) for x in (attr.get("media") or [])]
    media_refs: list[MediaRef] = []
    for mid in media_ids:
        if mid in media_index:
            media_refs.append(media_index[mid].model_copy(deep=True))
        else:
            media_refs.append(
                MediaRef(
                    media_id=mid,
                    resolved_url=None,
                    available=False,
                    warning="media_not_in_lesson_index",
                )
            )
            warnings.append(f"media_unresolved:{mid}")

    flip_cards: list[FlipCard] = []
    img_marks: list[ImgMark] = []
    chart_summary = ""
    text_plain = ""
    text_html_safe = ""

    if kind is BlockKind.RICH_TEXT:
        text_html_safe = sanitize_html_fragment(raw_text if isinstance(raw_text, str) else None)
        text_plain = html_to_plain(raw_text if isinstance(raw_text, str) else None)
    elif kind is BlockKind.AI_IMG:
        parsed = _parse_jsonish(raw_text if isinstance(raw_text, str) else None)
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                img_marks.append(
                    ImgMark(
                        object=item.get("object"),
                        description=item.get("description"),
                        mark_title=str(item.get("markTitle")) if item.get("markTitle") is not None else None,
                        x=item.get("x"),
                        y=item.get("y"),
                    )
                )
            text_plain = "\n".join(
                filter(
                    None,
                    [
                        " — ".join(filter(None, [m.mark_title, m.object, m.description]))
                        for m in img_marks
                    ],
                )
            )
        elif raw_text is None:
            warnings.append("aiimg_empty_annotations")
        else:
            warnings.append("aiimg_unparsed_annotations")
            text_plain = html_to_plain(str(raw_text))
    elif kind is BlockKind.AI_CHART:
        text_html_safe = ""  # never embed original widget scripts
        text_plain = html_to_plain(raw_text if isinstance(raw_text, str) else None)
        chart_summary = text_plain
        if not text_plain:
            warnings.append("aichart_empty_after_strip")
    elif kind is BlockKind.FLIP_CARD:
        parsed = _parse_jsonish(raw_text if isinstance(raw_text, str) else None)
        items = parsed if isinstance(parsed, list) else ([parsed] if isinstance(parsed, dict) else [])
        for item in items:
            if not isinstance(item, dict):
                continue
            front = item.get("front") or {}
            back = item.get("back") or {}
            flip_cards.append(
                FlipCard(
                    front=FlipSide(
                        title=str(front.get("title") or ""),
                        description=str(front.get("description") or ""),
                    ),
                    back=FlipSide(
                        title=str(back.get("title") or ""),
                        description=str(back.get("description") or ""),
                    ),
                )
            )
        text_plain = "\n".join(
            f"{c.front.title}: {c.front.description} / {c.back.title}: {c.back.description}"
            for c in flip_cards
        )
    elif kind in {BlockKind.AI_GAME, BlockKind.ROLE_PLAY, BlockKind.UNKNOWN}:
        text_plain = html_to_plain(raw_text if isinstance(raw_text, str) else None) or (
            str(raw_text).strip() if raw_text else ""
        )
        desc = attr.get("description")
        if desc:
            text_plain = (text_plain + "\n" + html_to_plain(str(desc))).strip()

    return LessonBlock(
        id=attr.get("id", 0),
        kind=kind,
        order_num=int(attr.get("orderNum") or 0),
        raw_name=None if raw_name is None else str(raw_name),
        text_plain=text_plain,
        text_html_safe=text_html_safe,
        media_ids=media_ids,
        media=media_refs,
        flip_cards=flip_cards,
        img_marks=img_marks,
        chart_summary=chart_summary,
        warnings=warnings,
        source={"id": attr.get("id"), "name": raw_name, "type": attr.get("type")},
    )


def normalize_lesson(step: dict[str, Any]) -> Lesson:
    scheme = step.get("scheme_description") or {}
    media_index = _build_media_index(step)
    attrs = ((step.get("step_info") or {}).get("attributes")) or []
    blocks = [_normalize_block(a, media_index) for a in attrs if isinstance(a, dict)]
    blocks.sort(key=lambda b: b.order_num)
    warnings: list[str] = []
    for b in blocks:
        warnings.extend(f"block:{b.id}:{w}" for w in b.warnings)
    return Lesson(
        id=int(step["id"]),
        code=str(step.get("code") or f"Lesson {step['id']}"),
        description=str(step.get("description") or ""),
        order_num=int(step.get("order_num") or 0),
        is_test=bool(scheme.get("isTest")),
        blocks=blocks,
        media_index=media_index,
        warnings=warnings,
    )


def merge_lessons(lessons: list[Lesson]) -> Lesson:
    if len(lessons) == 1:
        return lessons[0]
    if not lessons:
        raise ValueError("No lessons to merge")
    merged_blocks: list[LessonBlock] = []
    media_index: dict[int, MediaRef] = {}
    warnings: list[str] = []
    order = 0
    for lesson in lessons:
        media_index.update(lesson.media_index)
        warnings.extend(lesson.warnings)
        for block in lesson.blocks:
            copy = block.model_copy(deep=True)
            order += 1
            copy.order_num = order
            merged_blocks.append(copy)
    codes = " + ".join(l.code for l in lessons)
    description = "\n\n".join(filter(None, (l.description for l in lessons)))
    return Lesson(
        id=lessons[0].id,
        code=codes,
        description=description,
        order_num=lessons[0].order_num,
        is_test=False,
        blocks=merged_blocks,
        media_index=media_index,
        warnings=warnings
        + [f"merged_from:{','.join(str(l.id) for l in lessons)}"],
    )
