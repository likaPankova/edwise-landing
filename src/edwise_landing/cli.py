from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .pipeline import run_pipeline

console = Console()

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data"


@click.group()
def main() -> None:
    """Edwise lesson landing generator."""


@main.command("generate")
@click.option("--course", "course_path", type=click.Path(exists=True, dir_okay=False), required=True, help="Path to course JSON")
@click.option("--lesson", "lesson_ids", multiple=True, type=int, required=True, help="Lesson id(s); pass twice to merge")
@click.option("--out", "out_dir", type=click.Path(file_okay=False), default="outputs", show_default=True)
@click.option("--mode", type=click.Choice(["auto", "offline", "llm", "llm-html"]), default="auto", show_default=True)
@click.option("--tag", "out_tag", default=None, help="Optional output filename suffix, e.g. sonet_full")
@click.option(
    "--prev-html",
    "prev_html_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Seed style from HTML when course style lock does not exist yet (llm-html)",
)
@click.option(
    "--course-style",
    "course_style_path",
    type=click.Path(dir_okay=False),
    default=None,
    help="Path to course style lock JSON (default: outputs/course_styles/<course>_style.json)",
)
@click.option(
    "--relock-style",
    is_flag=True,
    help="Overwrite course style lock from this generation (llm-html)",
)
@click.option(
    "--css-template",
    "use_css_template",
    is_flag=True,
    help="Use shared course_base.css instead of model-generated styles",
)
@click.option("--no-media", is_flag=True, help="Skip media download")
@click.option("--no-embed", is_flag=True, help="Do not embed media as data URIs")
def generate(
    course_path: str,
    lesson_ids: tuple[int, ...],
    out_dir: str,
    mode: str,
    out_tag: str | None,
    prev_html_path: str | None,
    course_style_path: str | None,
    relock_style: bool,
    use_css_template: bool,
    no_media: bool,
    no_embed: bool,
) -> None:
    """Generate a standalone HTML landing for one or more lessons."""
    report = run_pipeline(
        course_path,
        list(lesson_ids),
        out_dir=out_dir,
        mode=mode,
        download_media=not no_media,
        embed_media=not no_embed,
        project_root=Path.cwd(),
        out_tag=out_tag,
        prev_html_path=prev_html_path,
        course_style_path=course_style_path,
        relock_style=relock_style,
        use_css_template=use_css_template,
    )
    table = Table(title="Edwise landing run")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("mode", report.mode)
    table.add_row("lessons", ", ".join(map(str, report.lesson_ids)))
    table.add_row("html", report.output_html)
    table.add_row("report", report.output_report)
    table.add_row("coverage", f"{report.coverage.covered}/{report.coverage.total}")
    table.add_row("missing_required", str(len(report.coverage.missing)))
    table.add_row("tech_ok", str(report.tech.ok))
    table.add_row("warnings", str(len(report.warnings)))
    table.add_row("total_sec", f"{report.timing.get('total', 0):.2f}")
    console.print(table)
    if report.coverage.missing:
        console.print("[yellow]Missing facts:[/yellow]")
        for m in report.coverage.missing[:12]:
            console.print(f"  - {m.fact_id}: {m.text[:120]}")
    if report.tech.issues:
        console.print("[cyan]Tech issues:[/cyan]")
        for i in report.tech.issues:
            console.print(f"  - [{i.severity}] {i.code}: {i.message}")


@main.command("scenario")
@click.argument("name", type=click.Choice(["A", "B", "C"]))
@click.option("--mode", type=click.Choice(["auto", "offline", "llm", "llm-html"]), default="offline", show_default=True)
@click.option("--tag", "out_tag", default=None, help="Optional output filename suffix")
@click.option("--out", "out_dir", type=click.Path(file_okay=False), default="outputs", show_default=True)
def scenario(name: str, mode: str, out_tag: str | None, out_dir: str) -> None:
    """Run acceptance scenarios A/B/C from the task brief."""
    data = DEFAULT_DATA
    if name == "A":
        course = data / "4794.json"
        ids = [117683, 117684]
    elif name == "B":
        course = data / "4763.json"
        ids = [115730]
    else:
        course = data / "4763.json"
        ids = [115730]
        # C uses same lesson but we force degraded media by skipping download
        report = run_pipeline(
            course,
            ids,
            out_dir=out_dir,
            mode=mode,
            download_media=False,
            embed_media=False,
            project_root=Path.cwd(),
            out_tag=out_tag,
        )
        console.print_json(json.dumps(report.model_dump(), ensure_ascii=False))
        return

    report = run_pipeline(
        course,
        ids,
        out_dir=out_dir,
        mode=mode,
        download_media=True,
        embed_media=True,
        project_root=Path.cwd(),
        out_tag=out_tag,
    )
    console.print(f"[green]HTML:[/green] {report.output_html}")
    console.print(
        f"coverage={report.coverage.covered}/{report.coverage.total} "
        f"missing={len(report.coverage.missing)} tech_ok={report.tech.ok} mode={report.mode}"
    )


if __name__ == "__main__":
    main()
