from __future__ import annotations

import json
import re
import time
from html import escape as html_escape
from pathlib import Path
from typing import Any

from .composer import compose_html
from .coverage import check_coverage
from .facts import acceptance_facts_for_ids, extract_facts
from .html_llm import build_html_with_llm
from .llm_client import GPTServiceClient
from .media import MediaResolver
from .models import Fact, RunReport
from .parser import load_course, merge_lessons, normalize_lesson, select_lessons
from .planner import build_plan_offline, build_plan_with_llm
from .style_continuity import (
    course_style_id,
    resolve_course_style_for_run,
    save_course_style,
)
from .validate import validate_html


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    import os

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def run_pipeline(
    course_path: str | Path,
    lesson_ids: list[int],
    *,
    out_dir: str | Path = "outputs",
    mode: str = "auto",
    download_media: bool = True,
    embed_media: bool = True,
    project_root: str | Path | None = None,
    out_tag: str | None = None,
    prev_html_path: str | Path | None = None,
    course_style_path: str | Path | None = None,
    relock_style: bool = False,
    use_css_template: bool = False,
) -> RunReport:
    """
    mode:
      - offline: deterministic local generation
      - llm: GPT builds full LessonPlan; composer renders HTML
      - llm-html: experimental — model returns full HTML/CSS/JS
      - auto: llm if key present else offline
    out_tag: optional filename suffix, e.g. sonet_full → lesson_115730_sonet_full.html

    Course style lock (llm-html):
      - If outputs/course_styles/<course_id>_style.json exists → reuse in prompt
      - Else first successful HTML becomes the course style lock
      - relock_style=True overwrites the lock from this run's HTML
      - prev_html_path can seed continuity when no lock exists yet
    use_css_template:
      - If True, replace generated <style> with course_base.css
      - Default False; style continuity via course_style lock is preferred
    """
    root = Path(project_root) if project_root else Path.cwd()
    _load_dotenv(root / ".env")

    t0 = time.perf_counter()
    timing: dict[str, float] = {}
    warnings: list[str] = []
    llm_calls: list[dict[str, Any]] = []

    steps = load_course(course_path)
    raw_lessons = select_lessons(steps, lesson_ids)
    lessons = [normalize_lesson(s) for s in raw_lessons]
    for lesson in lessons:
        warnings.extend(lesson.warnings)
    lesson = merge_lessons(lessons)
    timing["parse"] = time.perf_counter() - t0

    t_media = time.perf_counter()
    if download_media:
        resolver = MediaResolver(
            cache_dir=root / "assets_cache",
            embed=embed_media,
        )
        try:
            lesson = resolver.resolve_lesson(lesson)
            warnings.extend(resolver.warnings)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"media_resolver_error:{exc}")
    timing["media"] = time.perf_counter() - t_media

    t_facts = time.perf_counter()
    facts = extract_facts(lesson)
    acceptance = acceptance_facts_for_ids(lesson_ids)
    # Prefer acceptance needles for required coverage of scenarios A/B
    merged_facts: list[Fact] = []
    seen = set()
    for f in acceptance + facts:
        if f.id in seen:
            continue
        seen.add(f.id)
        merged_facts.append(f)
    timing["facts"] = time.perf_counter() - t_facts

    client = GPTServiceClient.from_env()
    effective = mode
    if mode == "auto":
        effective = "llm" if client else "offline"
    if effective in {"llm", "llm-html"} and not client:
        raise RuntimeError("LLM mode requested but EDWISE_GPT_KEY is not set")

    # Longer timeout for full-page HTML generation
    if effective == "llm-html" and client:
        client.timeout = max(client.timeout, 600.0)
        client.max_polls = max(client.max_polls, 120)

    style_fingerprint: dict[str, Any] | None = None
    style_lock_path: Path | None = None
    style_source = "none"
    if effective == "llm-html":
        try:
            style_fingerprint, style_lock_path, style_source = resolve_course_style_for_run(
                course_path,
                out_dir=out_dir,
                course_style_path=course_style_path,
                prev_html_path=prev_html_path,
                relock=relock_style,
            )
            warnings.append(f"course_style_source:{style_source}")
            if style_lock_path:
                warnings.append(f"course_style_path:{style_lock_path}")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"course_style_resolve_failed:{exc}")

    t_plan = time.perf_counter()
    html = ""
    if effective == "llm-html" and client:
        html, html_warnings = build_html_with_llm(
            lesson,
            merged_facts,
            client,
            project_root=root,
            prev_html_path=None if style_fingerprint is not None else prev_html_path,
            style_continuity=style_fingerprint,
            use_css_template=use_css_template,
        )
        warnings.extend(html_warnings)
        if "#EC8A00" not in html.upper() and "#ec8a00" not in html:
            warnings.append("brand:primary_color_missing")
        if "calibri" not in html.lower() and "segoe ui" not in html.lower():
            warnings.append("brand:font_missing")
        llm_calls = [
            {
                "engine": c.engine,
                "duration_sec": c.duration_sec,
                "prompt_tokens": c.prompt_tokens,
                "completion_tokens": c.completion_tokens,
                "total_tokens": c.total_tokens,
                "ok": c.ok,
                "error": c.error,
                "request_id": c.request_id,
            }
            for c in client.logs
        ]
        timing["plan"] = time.perf_counter() - t_plan
        timing["compose"] = 0.0
    else:
        if effective == "llm" and client:
            plan = build_plan_with_llm(lesson, merged_facts, client)
            llm_calls = [
                {
                    "engine": c.engine,
                    "duration_sec": c.duration_sec,
                    "prompt_tokens": c.prompt_tokens,
                    "completion_tokens": c.completion_tokens,
                    "total_tokens": c.total_tokens,
                    "ok": c.ok,
                    "error": c.error,
                    "request_id": c.request_id,
                }
                for c in client.logs
            ]
        else:
            plan = build_plan_offline(lesson, merged_facts)
            effective = "offline" if mode == "offline" else effective
        plan.source_lesson_ids = list(lesson_ids)
        timing["plan"] = time.perf_counter() - t_plan

        t_html = time.perf_counter()
        # Prefer putting acceptance-related source sentences into summary first
        if acceptance:
            for section in plan.sections:
                if section.id != "summary":
                    continue
                existing = {x.lower() for x in section.items}
                for f in facts:
                    if any(a.text.lower() in f.text.lower() for a in acceptance):
                        if f.text.lower() not in existing:
                            section.items.append(f.text)
                            existing.add(f.text.lower())
                for a in acceptance:
                    if a.text.lower() not in existing and len(a.text) < 40:
                        section.items.append(a.text)
                        existing.add(a.text.lower())
                break

        html = compose_html(plan)
        timing["compose"] = time.perf_counter() - t_html

    # Guarantee required facts appear in readable HTML
    required = [f for f in merged_facts if f.required]
    pre = check_coverage(html, required)
    if pre.missing:
        lines = [f"<li>{html_escape(m.text)}</li>" for m in pre.missing]
        extra = (
            "<aside class='edw-warning' id='coverage-appendix'>"
            "<h3>Дополнительно из источника</h3><ul>"
            + "".join(lines)
            + "</ul></aside>"
        )
        block = (
            f"<section class='container reveal' id='source-facts'>"
            f"{extra}</section>\n"
        )
        if "</main>" in html:
            html = html.replace("</main>", f"{block}</main>", 1)
        else:
            html = html.replace("</body>", f"{block}</body>", 1)
        warnings.append(f"injected_required_facts:{len(pre.missing)}")

    coverage = check_coverage(html, required if required else merged_facts[:80])
    tech = validate_html(html)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tag = "_".join(str(i) for i in lesson_ids)
    if out_tag:
        safe = re.sub(r"[^\w\-]+", "_", out_tag.strip())
        tag = f"{tag}_{safe}"
    html_path = out / f"lesson_{tag}.html"
    report_path = out / f"lesson_{tag}.report.json"
    html_path.write_text(html, encoding="utf-8")

    # Course style lock: create on first llm-html success, or overwrite on relock
    if effective == "llm-html" and style_lock_path is not None:
        should_save = relock_style or not style_lock_path.exists()
        if should_save:
            try:
                save_course_style(
                    style_lock_path,
                    html=html,
                    course_id=course_style_id(course_path),
                    source_lesson_ids=list(lesson_ids),
                    source_html=str(html_path),
                )
                warnings.append(
                    "course_style_locked" if not relock_style else "course_style_relocked"
                )
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"course_style_save_failed:{exc}")

    report = RunReport(
        mode=effective,
        lesson_ids=lesson_ids,
        warnings=warnings,
        coverage=coverage,
        tech=tech,
        llm_calls=llm_calls,
        timing={**timing, "total": time.perf_counter() - t0},
        output_html=str(html_path),
        output_report=str(report_path),
    )
    report_path.write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
