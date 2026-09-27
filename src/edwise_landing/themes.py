from __future__ import annotations

import re

from .models import ThemeTokens


SALES_THEME = ThemeTokens(
    metaphor="утренний шоу-рум перед первым клиентом",
    ink="#16242C",
    paper="#ECF0F1",
    accent="#FFB21A",
    accent_2="#2AFFEE",
    dark="#1B2830",
    warning="#C97A00",
    font_display="'Unbounded', 'Arial Black', Arial, sans-serif",
    font_body="'Golos Text', 'Segoe UI', Arial, sans-serif",
)

INDUSTRIAL_THEME = ThemeTokens(
    metaphor="щит управления и прогрев линии перед сливом",
    ink="#102018",
    paper="#E8EEE9",
    accent="#E3A008",
    accent_2="#3DDC97",
    dark="#0B1610",
    warning="#D97706",
    font_display="'Unbounded', 'Arial Black', Arial, sans-serif",
    font_body="'Manrope', 'Segoe UI', Arial, sans-serif",
)

DEFAULT_THEME = ThemeTokens(
    metaphor="образовательный маршрут",
    ink="#1A1F2C",
    paper="#F2F4F7",
    accent="#0EA5A0",
    accent_2="#F59E0B",
    dark="#111827",
    warning="#B45309",
    font_display="'Unbounded', 'Arial Black', Arial, sans-serif",
    font_body="'Manrope', 'Segoe UI', Arial, sans-serif",
)


def pick_theme(text_blob: str) -> ThemeTokens:
    t = text_blob.lower()
    sales_hit = bool(
        re.search(r"клиент|продаж|шоу-?рум|\bvin\b|чек-?лист|план[её]рк", t)
    )
    industrial_hit = bool(
        re.search(
            r"\bсиз\b|щу\s*\d+|трубопровод|\bслив[аеу]?\b|поддон|прогрев\s+трубопровод",
            t,
        )
    )
    # Prefer the domain with clearer signal; sales first on ties for commercial courses.
    if sales_hit and not industrial_hit:
        return SALES_THEME.model_copy(deep=True)
    if industrial_hit and not sales_hit:
        return INDUSTRIAL_THEME.model_copy(deep=True)
    if sales_hit:
        return SALES_THEME.model_copy(deep=True)
    if industrial_hit:
        return INDUSTRIAL_THEME.model_copy(deep=True)
    return DEFAULT_THEME.model_copy(deep=True)
