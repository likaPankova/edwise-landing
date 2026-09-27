from __future__ import annotations

from pathlib import Path

from edwise_landing.parser import load_course, normalize_lesson, select_lessons
from edwise_landing.pipeline import run_pipeline

DATA = Path(__file__).resolve().parents[1] / "data"


def test_normalize_4763_handles_null_aiimg():
    steps = load_course(DATA / "4763.json")
    lesson = normalize_lesson(select_lessons(steps, [115730])[0])
    assert lesson.id == 115730
    null_img = next(b for b in lesson.blocks if b.id == 6)
    assert "text_literal_null" in null_img.warnings


def test_scenario_b_offline(tmp_path: Path):
    report = run_pipeline(
        DATA / "4763.json",
        [115730],
        out_dir=tmp_path,
        mode="offline",
        download_media=False,
        project_root=tmp_path,
    )
    assert Path(report.output_html).exists()
    assert report.tech.ok
    # acceptance needles should be covered
    missing_ids = {m.fact_id for m in report.coverage.missing if m.fact_id.startswith(("ppe", "shu", "warm", "ind", "pal", "box", "no_"))}
    assert not missing_ids, missing_ids


def test_course_style_lock_roundtrip(tmp_path: Path):
    from edwise_landing.style_continuity import (
        default_course_style_path,
        load_style_continuity,
        resolve_course_style_for_run,
        save_course_style,
    )

    sample = tmp_path / "sample.html"
    sample.write_text(
        """<!DOCTYPE html><html><head><style>
        :root{--edw-primary:#EC8A00;}
        .hero{min-height:640px;align-items:flex-end;}
        .flip-wrap{display:flex;justify-content:center;}
        </style></head><body>
        <h1>Demo</h1><p class="lead">Порядок действий оператора на линии перед запуском.</p>
        <div class="flip-wrap"><div class="flip-card"></div></div>
        </body></html>""",
        encoding="utf-8",
    )
    course = tmp_path / "4763.json"
    course.write_text("[]", encoding="utf-8")
    lock = default_course_style_path(course, out_dir=tmp_path)
    save_course_style(lock, html=sample, course_id="4763", source_lesson_ids=[1])
    fp, path, src = resolve_course_style_for_run(course, out_dir=tmp_path)
    assert src == "course_style"
    assert path == lock
    assert fp is not None
    assert "#EC8A00" in fp["css_root"]
    assert load_style_continuity(lock)["css_root"] == fp["css_root"]


def test_component_catalog_loads():
    from edwise_landing.component_catalog import catalog_for_prompt, load_course_base_css

    cat = catalog_for_prompt()
    assert cat["components"]
    ids = {c["id"] for c in cat["components"]}
    assert {"hero", "flip_card", "quiz", "steps"} <= ids
    css = load_course_base_css()
    assert ".flip-wrap" in css
    assert "hero--mid" in css
