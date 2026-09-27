from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_TEMPLATES = Path(__file__).resolve().parent / "templates"


def templates_dir() -> Path:
    return _TEMPLATES


@lru_cache(maxsize=4)
def load_component_catalog() -> dict[str, Any]:
    path = _TEMPLATES / "component_catalog.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("component_catalog.json must be an object")
    return data


def load_course_base_css() -> str:
    path = _TEMPLATES / "course_base.css"
    return path.read_text(encoding="utf-8")


def catalog_for_prompt(*, compact: bool = True) -> dict[str, Any]:
    """Shrink catalog for INPUT_JSON (save tokens, keep options)."""
    raw = load_component_catalog()
    components = []
    for c in raw.get("components") or []:
        variants = c.get("variants") or []
        if isinstance(variants, list) and variants and isinstance(variants[0], dict):
            v_ids = [v.get("id") for v in variants if isinstance(v, dict)]
            v_notes = {
                v["id"]: v.get("note")
                for v in variants
                if isinstance(v, dict) and v.get("id") and v.get("note")
            }
        else:
            v_ids = list(variants)
            v_notes = {}
        entry = {
            "id": c.get("id"),
            "required": bool(c.get("required")),
            "classes": c.get("classes") or [],
            "variant_ids": v_ids,
            "when": c.get("when"),
        }
        if v_notes and not compact:
            entry["variant_notes"] = v_notes
        if c.get("behavior"):
            entry["behavior"] = c["behavior"]
        components.append(entry)

    return {
        "principle": raw.get("principle"),
        "rules_for_llm": raw.get("rules_for_llm"),
        "css_template": raw.get("css_template"),
        "components": components,
        "example_compositions": raw.get("example_compositions"),
    }
