from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .models import TechIssue, TechReport


FORBIDDEN_JS = [
    re.compile(r"\beval\s*\("),
    re.compile(r"\bnew\s+Function\s*\("),
    re.compile(r"\bfetch\s*\("),
    re.compile(r"XMLHttpRequest"),
    re.compile(r"navigator\.sendBeacon"),
    re.compile(r"document\.write\s*\("),
]


def validate_html(html: str) -> TechReport:
    issues: list[TechIssue] = []
    if not html.lstrip().lower().startswith("<!doctype html"):
        issues.append(TechIssue(severity="error", code="doctype", message="Missing <!DOCTYPE html>"))

    soup = BeautifulSoup(html, "lxml")
    if not soup.find("html"):
        issues.append(TechIssue(severity="error", code="html", message="Missing <html>"))
    if not soup.find("main"):
        issues.append(TechIssue(severity="warn", code="main", message="Missing <main> landmark"))
    if not soup.find("meta", attrs={"name": "viewport"}):
        issues.append(TechIssue(severity="error", code="viewport", message="Missing viewport meta"))

    # scripts safety
    for script in soup.find_all("script"):
        src = script.get("src")
        if src and not str(src).startswith((".", "/", "data:")):
            # external script dependency — discouraged for critical path
            issues.append(
                TechIssue(
                    severity="warn",
                    code="external_script",
                    message=f"External script: {src}",
                )
            )
        body = script.string or ""
        for pat in FORBIDDEN_JS:
            if pat.search(body):
                issues.append(
                    TechIssue(
                        severity="error",
                        code="unsafe_js",
                        message=f"Forbidden JS pattern: {pat.pattern}",
                    )
                )

    # interactive a11y basics
    for btn in soup.find_all("button"):
        if not (btn.get_text(strip=True) or btn.get("aria-label")):
            issues.append(
                TechIssue(severity="warn", code="button_label", message="Button without accessible name")
            )

    # reduced motion mention
    style = "\n".join(s.get_text() for s in soup.find_all("style"))
    if "prefers-reduced-motion" not in style:
        issues.append(
            TechIssue(
                severity="warn",
                code="reduced_motion",
                message="CSS missing prefers-reduced-motion handling",
            )
        )

    # noscript fallback
    if not soup.find("noscript"):
        issues.append(
            TechIssue(severity="warn", code="noscript", message="Missing <noscript> fallback")
        )

    # crude overflow risk: fixed widths in px over 100%
    if re.search(r"width\s*:\s*(1[2-9]\d{2}|[2-9]\d{3})px", style):
        issues.append(
            TechIssue(
                severity="warn",
                code="fixed_width",
                message="Large fixed pixel widths may cause horizontal scroll",
            )
        )

    ok = not any(i.severity == "error" for i in issues)
    return TechReport(ok=ok, issues=issues)
