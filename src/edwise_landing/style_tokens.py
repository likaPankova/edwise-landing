from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_STYLE_PATH = "style_example.json"


def _project_style_path(root: Path | None = None) -> Path:
    base = root or Path.cwd()
    return base / DEFAULT_STYLE_PATH


def load_brand_style(path: str | Path | None = None, *, project_root: Path | None = None) -> dict[str, Any]:
    """Load brand style guide JSON for LLM HTML generation."""
    p = Path(path) if path else _project_style_path(project_root)
    if not p.exists():
        raise FileNotFoundError(f"Brand style file not found: {p}")

    raw = json.loads(p.read_text(encoding="utf-8"))
    normalized = raw.get("custom", {}).get("normalized", {})
    meta = normalized.get("metadata", {})
    palette = meta.get("palette", {})
    typography = meta.get("typography", {})
    radius = meta.get("radius", {})
    classes = normalized.get("classes", {})

    component_hints = {
        "edw-warning": "критичные запреты и условия",
        "edw-tip": "полезные подсказки",
        "edw-definition": "определения терминов",
        "edw-key-takeaway": "ключевой вывод",
        "edw-callout": "выделенный блок",
        "edw-example": "пример из практики",
        "edw-checklist": "чек-лист действий",
        "edw-steps": "пошаговый список",
        "edw-numeric": "важные числа и нормативы",
        "edw-emphasis": "акцент в тексте",
        "edw-section-heading": "заголовок секции",
        "edw-chart": "схема / диаграмма",
    }

    css_variables = {
        "--edw-primary": palette.get("primary", "#EC8A00"),
        "--edw-secondary": palette.get("secondary", "#8196A1"),
        "--edw-accent": palette.get("accent", "#D97706"),
        "--edw-text": palette.get("text", "#4F5B62"),
        "--edw-text-muted": palette.get("text-muted", "#6E7A82"),
        "--edw-background": palette.get("background", "#FFFFFF"),
        "--edw-surface": palette.get("surface", "#F5F7F8"),
        "--edw-border": palette.get("border", "#D5DCE0"),
        "--edw-success": palette.get("success", "#2E8B57"),
        "--edw-warning": palette.get("warning", "#C2410C"),
        "--edw-radius-sm": radius.get("sm", "4px"),
        "--edw-radius-md": radius.get("md", "8px"),
        "--edw-radius-lg": radius.get("lg", "12px"),
        "--edw-font-body": typography.get(
            "font-family-body",
            "Calibri, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
        ),
        "--edw-font-headings": typography.get(
            "font-family-headings",
            "Calibri, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif",
        ),
        "--edw-font-mono": typography.get(
            "font-family-mono",
            "'Cascadia Code', 'Consolas', 'Courier New', monospace",
        ),
        "--edw-base-size": typography.get("base-font-size", "16px"),
    }

    # Keep visual tokens only — do not surface organization name in the page UI.
    style_summary = str(meta.get("summary") or "")
    return {
        "source_file": str(p.name),
        "brand_color": raw.get("color"),
        "secondary_color": raw.get("custom", {}).get("secondaryColor"),
        "style_summary": style_summary,
        "palette": palette,
        "typography": typography,
        "radius": radius,
        "css_variables": css_variables,
        "heading_styles": normalized.get("tags", {}).get("h2", {}),
        "body_styles": normalized.get("tags", {}).get("p", {}),
        "component_classes": component_hints,
        "strict_rule": (
            "Используй СТРОГО эти токены и классы из style_example.json. "
            "Не подключай посторонние шрифты (Google Fonts и т.п.), "
            "не меняй палитру. Не выводи название организации/бренда текстом на странице."
        ),
    }
