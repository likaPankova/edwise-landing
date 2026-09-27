from __future__ import annotations

import re
import unicodedata

from .models import CoverageItem, CoverageReport, Fact


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[«»\"'`]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _present(needle: str, haystack: str) -> tuple[bool, str]:
    n = _norm(needle)
    h = _norm(haystack)
    if not n:
        return True, ""
    if n in h:
        idx = h.find(n)
        return True, haystack[max(0, idx) : max(0, idx) + min(120, len(needle))]
    # token overlap for soft acceptance needles
    tokens = [t for t in re.split(r"[^\w+]+", n) if len(t) > 2]
    if not tokens:
        return False, ""
    hit = sum(1 for t in tokens if t in h)
    ratio = hit / len(tokens)
    if ratio >= 0.7:
        return True, f"token_overlap={ratio:.2f}"
    return False, ""


def check_coverage(html: str, facts: list[Fact]) -> CoverageReport:
    items: list[CoverageItem] = []
    missing: list[CoverageItem] = []
    for fact in facts:
        ok, evidence = _present(fact.text, html)
        item = CoverageItem(
            fact_id=fact.id,
            text=fact.text,
            present=ok,
            evidence=evidence,
        )
        items.append(item)
        if fact.required and not ok:
            missing.append(item)
    covered = sum(1 for i in items if i.present)
    return CoverageReport(
        total=len(items),
        covered=covered,
        missing=missing,
        items=items,
    )
