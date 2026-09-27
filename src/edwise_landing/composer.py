from __future__ import annotations

import html
import json
from typing import Iterable

from .models import LessonPlan, PlanSection, SectionKind


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _render_items(items: Iterable[str], tag: str = "li") -> str:
    return "".join(f"<{tag}>{_esc(i)}</{tag}>" for i in items if i)


def _section_continue(next_id: str | None, label: str = "Дальше") -> str:
    if not next_id:
        return ""
    return f"""
    <div class="section-actions">
      <a class="btn btn-next" href="#{_esc(next_id)}">{_esc(label)}</a>
    </div>
    """


def _section_hero(plan: LessonPlan, s: PlanSection, next_id: str | None = None) -> str:
    return f"""
<section class="chapter hero" id="{_esc(s.id)}" data-reveal>
  <div class="wrap hero-grid">
    <div>
      <p class="eyebrow">Edwise</p>
      <h1>{_esc(plan.title)}</h1>
      <p class="lead">{_esc(s.lead or plan.subtitle)}</p>
      <div class="hero-actions">
        <a class="btn" href="#{_esc(next_id or 'goals')}">Начать</a>
      </div>
    </div>
    <div class="hero-visual" aria-hidden="true">
      <div class="orb"></div>
      <div class="orb orb-2"></div>
    </div>
  </div>
</section>
"""


def _section_goals(s: PlanSection, next_id: str | None = None) -> str:
    return f"""
<section class="chapter" id="{_esc(s.id)}" data-reveal>
  <div class="wrap prose">
    <h2>{_esc(s.title)}</h2>
    <ol class="goal-list">{_render_items(s.items)}</ol>
    {_section_continue(next_id, "Перейти к разбору")}
  </div>
</section>
"""


def _section_prose(s: PlanSection, next_id: str | None = None) -> str:
    paras = "".join(f"<p>{_esc(p.strip())}</p>" for p in s.body.split("\n\n") if p.strip())
    return f"""
<section class="chapter" id="{_esc(s.id)}" data-reveal>
  <div class="wrap prose">
    <h2>{_esc(s.title)}</h2>
    {paras}
    {_section_continue(next_id)}
  </div>
</section>
"""


def _section_definition(s: PlanSection, next_id: str | None = None) -> str:
    return f"""
<section class="chapter" id="{_esc(s.id)}" data-reveal>
  <div class="wrap">
    <article class="definition" aria-label="Определение">
      <h3>{_esc(s.title)}</h3>
      <p>{_esc(s.body)}</p>
    </article>
    {_section_continue(next_id)}
  </div>
</section>
"""


def _section_warning(s: PlanSection, next_id: str | None = None) -> str:
    return f"""
<section class="chapter" id="{_esc(s.id)}" data-reveal>
  <div class="wrap">
    <aside class="warning" role="note">
      <h3>{_esc(s.title)}</h3>
      <p>{_esc(s.body)}</p>
    </aside>
    {_section_continue(next_id)}
  </div>
</section>
"""


def _section_timeline(s: PlanSection, next_id: str | None = None) -> str:
    steps = []
    for i, item in enumerate(s.items, 1):
        steps.append(
            f"""
            <li>
              <button type="button" class="tl-btn" aria-expanded="false" data-tl="{i}">
                <span class="tl-num">{i}</span>
                <span>{_esc(item)}</span>
              </button>
            </li>
            """
        )
    return f"""
<section class="chapter chapter-dark" id="{_esc(s.id)}" data-reveal>
  <div class="wrap">
    <h2>{_esc(s.title)}</h2>
    <ol class="timeline">{''.join(steps)}</ol>
    {_section_continue(next_id)}
  </div>
</section>
"""


def _section_checklist(s: PlanSection, next_id: str | None = None) -> str:
    rows = []
    for i, item in enumerate(s.items):
        rows.append(
            f"""
            <label class="check-row">
              <input type="checkbox" data-check="{i}">
              <span>{_esc(item)}</span>
            </label>
            """
        )
    return f"""
<section class="chapter" id="{_esc(s.id)}" data-reveal>
  <div class="wrap">
    <h2>{_esc(s.title)}</h2>
    <p class="muted">Отметьте пункты. Прогресс сохраняется только в этой вкладке.</p>
    <div class="checklist" role="group" aria-label="{_esc(s.title)}">{''.join(rows)}</div>
    <p class="check-status" aria-live="polite">Готово: 0 / {len(s.items)}</p>
    {_section_continue(next_id)}
  </div>
</section>
"""


def _section_flip(s: PlanSection, next_id: str | None = None) -> str:
    cards = []
    for i, pair in enumerate(s.pairs):
        cards.append(
            f"""
            <button type="button" class="flip" data-flip="{i}" aria-pressed="false">
              <span class="flip-face flip-front">
                <strong>{_esc(pair.get('front_title', ''))}</strong>
                <span>{_esc(pair.get('front_body', ''))}</span>
              </span>
              <span class="flip-face flip-back">
                <strong>{_esc(pair.get('back_title', ''))}</strong>
                <span>{_esc(pair.get('back_body', ''))}</span>
              </span>
            </button>
            """
        )
    return f"""
<section class="chapter" id="{_esc(s.id)}" data-reveal>
  <div class="wrap">
    <h2>{_esc(s.title)}</h2>
    <p class="muted">Нажмите карточку или Enter/Space, чтобы перевернуть.</p>
    <div class="flip-grid">{''.join(cards)}</div>
    {_section_continue(next_id)}
  </div>
</section>
"""


def _section_quiz(s: PlanSection, next_id: str | None = None) -> str:
    blocks = []
    for i, q in enumerate(s.quiz):
        blocks.append(
            f"""
            <fieldset class="quiz-item" data-quiz="{i}" data-answer="{str(bool(q.get('answer'))).lower()}">
              <legend>{_esc(str(q.get('question', '')))}</legend>
              <div class="quiz-actions">
                <button type="button" data-val="true">Верно</button>
                <button type="button" data-val="false">Неверно</button>
              </div>
              <p class="quiz-feedback" hidden>{_esc(str(q.get('explain', '')))}</p>
            </fieldset>
            """
        )
    return f"""
<section class="chapter chapter-dark" id="{_esc(s.id)}" data-reveal>
  <div class="wrap">
    <h2>{_esc(s.title)}</h2>
    <form class="quiz" onsubmit="return false;">{''.join(blocks)}</form>
    {_section_continue(next_id, "К итогам")}
  </div>
</section>
"""


def _section_media(s: PlanSection, next_id: str | None = None) -> str:
    panels: list[str] = []
    for m in s.media:
        src = m.data_uri or m.resolved_url
        caption = s.body or m.name or ""
        marks = "".join(f"<li>{_esc(i)}</li>" for i in s.items if i)
        if m.available and src and (m.mimetype or "").startswith("image/"):
            panels.append(
                f"""
                <figure class="visual-stage">
                  <div class="visual-frame">
                    <img src="{_esc(src)}" alt="{_esc(m.name or s.title)}">
                  </div>
                  <figcaption class="visual-caption">
                    <p class="eyebrow">Схема</p>
                    <h2>{_esc(s.title)}</h2>
                    <p>{_esc(caption)}</p>
                    {f'<ul class="mark-list">{marks}</ul>' if marks else ''}
                    {_section_continue(next_id)}
                  </figcaption>
                </figure>
                """
            )
        elif not m.available:
            panels.append(
                f"""
                <div class="media-missing" role="status">
                  <p class="eyebrow">Медиа недоступно · id {m.media_id}</p>
                  <h2>{_esc(s.title)}</h2>
                  <p>{_esc(caption or "Подпись сохранена без изображения.")}</p>
                  {f'<ul class="mark-list">{marks}</ul>' if marks else ''}
                  {_section_continue(next_id)}
                </div>
                """
            )
    if not panels:
        panels.append(
            f"<div class='wrap prose'><h2>{_esc(s.title)}</h2><p>{_esc(s.body)}</p>{_section_continue(next_id)}</div>"
        )
    return f"""
<section class="chapter chapter-visual" id="{_esc(s.id)}" data-reveal>
  {''.join(panels)}
</section>
"""


def _section_practice(s: PlanSection, next_id: str | None = None) -> str:
    return f"""
<section class="chapter" id="{_esc(s.id)}" data-reveal>
  <div class="wrap prose">
    <h2>{_esc(s.title)}</h2>
    <p>{_esc(s.body)}</p>
    {_section_continue(next_id)}
  </div>
</section>
"""


def _section_summary(s: PlanSection, next_id: str | None = None) -> str:
    return f"""
<section class="chapter summary" id="{_esc(s.id)}" data-reveal>
  <div class="wrap">
    <h2>{_esc(s.title)}</h2>
    <ul class="summary-list">{_render_items(s.items)}</ul>
    {_section_continue(next_id, "В начало") if next_id else '<p class="muted">Урок завершён — можно вернуться к любому блоку через прокрутку.</p>'}
  </div>
</section>
"""


RENDERERS = {
    SectionKind.HERO: lambda plan, s, nxt: _section_hero(plan, s, nxt),
    SectionKind.GOALS: lambda plan, s, nxt: _section_goals(s, nxt),
    SectionKind.PROSE: lambda plan, s, nxt: _section_prose(s, nxt),
    SectionKind.DEFINITION: lambda plan, s, nxt: _section_definition(s, nxt),
    SectionKind.WARNING: lambda plan, s, nxt: _section_warning(s, nxt),
    SectionKind.TIMELINE: lambda plan, s, nxt: _section_timeline(s, nxt),
    SectionKind.CHECKLIST: lambda plan, s, nxt: _section_checklist(s, nxt),
    SectionKind.FLIP: lambda plan, s, nxt: _section_flip(s, nxt),
    SectionKind.QUIZ: lambda plan, s, nxt: _section_quiz(s, nxt),
    SectionKind.MEDIA: lambda plan, s, nxt: _section_media(s, nxt),
    SectionKind.PRACTICE: lambda plan, s, nxt: _section_practice(s, nxt),
    SectionKind.SUMMARY: lambda plan, s, nxt: _section_summary(s, nxt),
    SectionKind.CARDS: lambda plan, s, nxt: _section_checklist(s, nxt),
}


BASE_CSS = """
:root {
  --ink: __INK__;
  --paper: __PAPER__;
  --accent: __ACCENT__;
  --accent-2: __ACCENT_2__;
  --dark: __DARK__;
  --warning: __WARNING__;
  --muted: color-mix(in srgb, var(--ink) 62%, white);
  --line: color-mix(in srgb, var(--ink) 16%, white);
  --f-display: __FONT_DISPLAY__;
  --f-body: __FONT_BODY__;
  --col: 68ch;
  --radius: 18px;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  color: var(--ink);
  background:
    radial-gradient(1200px 600px at 10% -10%, color-mix(in srgb, var(--accent-2) 18%, transparent), transparent 55%),
    radial-gradient(900px 500px at 100% 0%, color-mix(in srgb, var(--accent) 16%, transparent), transparent 50%),
    var(--paper);
  font: 400 18px/1.62 var(--f-body);
  -webkit-font-smoothing: antialiased;
}
img { max-width: 100%; display: block; }

button, a.btn { font: inherit; }
:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
.wrap { width: min(1120px, calc(100% - 32px)); margin-inline: auto; }
.prose { max-width: var(--col); }
.prose p { margin: 0 0 1em; }
h1,h2,h3 { font-family: var(--f-display); font-weight: 600; letter-spacing: -0.02em; margin: 0 0 0.55em; line-height: 1.1; }
h1 { font-size: clamp(34px, 7vw, 72px); max-width: 16ch; }
h2 { font-size: clamp(26px, 4vw, 46px); }
h3 { font-size: clamp(20px, 2.4vw, 28px); }
.lead { font-size: clamp(18px, 2vw, 22px); color: color-mix(in srgb, var(--ink) 88%, white); max-width: 42ch; }
.muted { color: var(--muted); }
.eyebrow { text-transform: uppercase; letter-spacing: 0.14em; font-size: 12px; font-weight: 700; color: color-mix(in srgb, var(--accent-2) 70%, var(--ink)); }
.chapter { padding: clamp(64px, 10vw, 120px) 0; }
.chapter-dark { background: var(--dark); color: #E8EEF0; }
.chapter-dark .muted { color: #A8B4BA; }
.progress { position: fixed; inset: 0 0 auto; height: 4px; z-index: 40; background: rgba(0,0,0,.08); }
.progress > span { display: block; height: 100%; width: 0; background: linear-gradient(90deg, var(--accent-2), var(--accent)); }
.hero-grid { display: grid; gap: 40px; align-items: center; min-height: min(88vh, 820px); }
@media (min-width: 900px) { .hero-grid { grid-template-columns: 1.15fr .85fr; } }
.hero-actions { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; margin-top: 28px; }
.btn {
  display: inline-flex; align-items: center; justify-content: center;
  text-decoration: none; color: var(--dark); background: var(--accent);
  padding: 12px 18px; border-radius: 999px; font-weight: 700;
}
.section-actions { margin-top: 28px; }
.btn-next { box-shadow: 0 10px 28px color-mix(in srgb, var(--accent) 35%, transparent); }
.chapter-dark .btn, .chapter-visual .btn { color: var(--dark); }

.hero-visual { position: relative; min-height: 280px; }
.orb {
  position: absolute; inset: 12% 18%; border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, var(--accent-2), transparent 55%),
              radial-gradient(circle at 70% 70%, var(--accent), transparent 50%),
              color-mix(in srgb, var(--dark) 80%, black);
  filter: blur(0px); opacity: .9;
  animation: drift 9s ease-in-out infinite alternate;
}
.orb-2 { inset: 28% 8% 8% 38%; opacity: .55; animation-delay: -3s; }
.hero-badge {
  position: absolute; left: 8%; bottom: 8%; margin: 0; padding: 10px 14px;
  background: color-mix(in srgb, var(--paper) 88%, white); color: var(--ink);
  border-radius: 999px; font-size: 14px; font-weight: 700;
}
.goal-list, .summary-list, .mark-list { padding-left: 1.2em; }
.goal-list li, .summary-list li { margin: 0.55em 0; }
.definition, .warning {
  border-radius: var(--radius); padding: 22px 24px; border: 1px solid var(--line);
  background: color-mix(in srgb, var(--paper) 70%, white);
}
.definition { border-left: 5px solid var(--accent-2); }
.warning { border-left: 5px solid var(--warning); background: color-mix(in srgb, var(--warning) 10%, white); }
.timeline { list-style: none; padding: 0; margin: 0; display: grid; gap: 12px; }
.tl-btn {
  width: 100%; text-align: left; display: flex; gap: 14px; align-items: flex-start;
  border: 1px solid color-mix(in srgb, white 18%, transparent); background: color-mix(in srgb, white 6%, transparent);
  color: inherit; border-radius: 14px; padding: 14px 16px; cursor: pointer;
}
.tl-btn[aria-expanded="true"] { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 16%, transparent); }
.tl-num {
  flex: 0 0 auto; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center;
  background: var(--accent); color: var(--dark); font-weight: 800; font-size: 14px;
}
.checklist { display: grid; gap: 10px; margin-top: 18px; }
.check-row {
  display: flex; gap: 12px; align-items: flex-start; padding: 12px 14px;
  border: 1px solid var(--line); border-radius: 12px; background: color-mix(in srgb, white 70%, var(--paper));
  cursor: pointer;
}
.check-row input { margin-top: 4px; width: 18px; height: 18px; }
.flip-grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.flip {
  position: relative; min-height: 220px; border: 0; padding: 0; cursor: pointer;
  background: transparent; perspective: 1000px;
}
.flip-face {
  position: absolute; inset: 0; border-radius: var(--radius); padding: 18px;
  display: grid; align-content: start; gap: 10px; text-align: left;
  border: 1px solid var(--line); background: white;
  backface-visibility: hidden; transition: transform .5s ease;
}
.flip-front { transform: rotateY(0deg); }
.flip-back {
  transform: rotateY(180deg);
  background: var(--dark); color: #E8EEF0; border-color: transparent;
}
.flip[aria-pressed="true"] .flip-front { transform: rotateY(180deg); }
.flip[aria-pressed="true"] .flip-back { transform: rotateY(360deg); }
.quiz { display: grid; gap: 18px; }
.quiz-item { border: 1px solid color-mix(in srgb, white 18%, transparent); border-radius: 14px; padding: 14px 16px; }
.quiz-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
.quiz-actions button {
  border: 0; border-radius: 999px; padding: 8px 14px; cursor: pointer;
  background: var(--accent); color: var(--dark); font-weight: 700;
}
.quiz-feedback { margin: 10px 0 0; color: var(--accent-2); }
.chapter-visual {
  padding: clamp(48px, 8vw, 96px) 0;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--dark) 92%, black), var(--dark));
  color: #E8EEF0;
}
.visual-stage {
  width: min(1180px, calc(100% - 24px));
  margin: 0 auto;
  display: grid;
  gap: clamp(20px, 4vw, 36px);
  align-items: center;
}
@media (min-width: 900px) {
  .visual-stage { grid-template-columns: 1.35fr 0.85fr; }
}
.visual-frame {
  position: relative;
  border-radius: 28px;
  overflow: hidden;
  background:
    radial-gradient(circle at 20% 15%, color-mix(in srgb, var(--accent-2) 28%, transparent), transparent 45%),
    radial-gradient(circle at 80% 80%, color-mix(in srgb, var(--accent) 22%, transparent), transparent 40%),
    color-mix(in srgb, var(--dark) 70%, #000);
  box-shadow: 0 30px 80px rgba(0,0,0,.35);
  isolation: isolate;
}
.visual-frame::after {
  content: "";
  position: absolute; inset: 0;
  pointer-events: none;
  border-radius: inherit;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, white 14%, transparent);
}
.visual-frame img {
  width: calc(100% - 28px);
  margin: 14px;
  height: auto;
  display: block;
  border-radius: 18px;
  background: #F7F8F8;
  box-shadow: 0 12px 36px rgba(0,0,0,.22);
}
.visual-caption h2 { color: #fff; margin-bottom: 12px; }
.visual-caption p { margin: 0 0 12px; color: #C9D5D8; max-width: 36ch; }
.visual-caption .mark-list { color: #E8EEF0; }
.media-missing {
  width: min(900px, calc(100% - 32px));
  margin: 0 auto;
  padding: 22px 24px;
  border-radius: 18px;
  border: 1px dashed color-mix(in srgb, var(--accent) 45%, white);
  background: color-mix(in srgb, var(--warning) 12%, var(--dark));
}
.summary { background: color-mix(in srgb, var(--accent-2) 10%, var(--paper)); }

[data-reveal] { opacity: 1; transform: none; }
@media (prefers-reduced-motion: no-preference) {
  [data-reveal] { opacity: 0; transform: translateY(18px); transition: opacity .6s ease, transform .6s ease; }
  [data-reveal].is-in { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  .orb { animation: none; }
  .flip-face { transition: none; }
}
@keyframes drift {
  from { transform: translate3d(0,0,0) scale(1); }
  to { transform: translate3d(12px,-10px,0) scale(1.04); }
}
@media (max-width: 767px) {
  body { font-size: 16px; }
  .wrap { width: min(1120px, calc(100% - 24px)); }
}
"""


BASE_JS = r"""
(function () {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const bar = document.querySelector('.progress > span');
  function onScroll() {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const p = max > 0 ? (window.scrollY / max) * 100 : 0;
    if (bar) bar.style.width = p + '%';
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  if (!reduce && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) e.target.classList.add('is-in'); });
    }, { threshold: 0.12 });
    document.querySelectorAll('[data-reveal]').forEach((el) => io.observe(el));
  } else {
    document.querySelectorAll('[data-reveal]').forEach((el) => el.classList.add('is-in'));
  }

  document.querySelectorAll('.tl-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const open = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', open ? 'false' : 'true');
    });
  });

  const checks = Array.from(document.querySelectorAll('[data-check]'));
  const status = document.querySelector('.check-status');
  function updateChecks() {
    const done = checks.filter((c) => c.checked).length;
    if (status) status.textContent = 'Готово: ' + done + ' / ' + checks.length;
  }
  checks.forEach((c) => c.addEventListener('change', updateChecks));
  updateChecks();

  document.querySelectorAll('.flip').forEach((btn) => {
    function toggle() {
      const pressed = btn.getAttribute('aria-pressed') === 'true';
      btn.setAttribute('aria-pressed', pressed ? 'false' : 'true');
    }
    btn.addEventListener('click', toggle);
    btn.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
    });
  });

  document.querySelectorAll('.quiz-item').forEach((item) => {
    const expected = item.getAttribute('data-answer') === 'true';
    const feedback = item.querySelector('.quiz-feedback');
    item.querySelectorAll('button[data-val]').forEach((b) => {
      b.addEventListener('click', () => {
        const val = b.getAttribute('data-val') === 'true';
        if (feedback) {
          feedback.hidden = false;
          feedback.textContent = (val === expected ? 'Верно. ' : 'Неверно. ') + (feedback.textContent || '');
        }
      });
    });
  });
})();
"""


def compose_html(plan: LessonPlan, *, extra_noscript: str = "") -> str:
    theme = plan.theme
    css = (
        BASE_CSS.replace("__INK__", theme.ink)
        .replace("__PAPER__", theme.paper)
        .replace("__ACCENT__", theme.accent)
        .replace("__ACCENT_2__", theme.accent_2)
        .replace("__DARK__", theme.dark)
        .replace("__WARNING__", theme.warning)
        .replace("__FONT_DISPLAY__", theme.font_display)
        .replace("__FONT_BODY__", theme.font_body)
    )
    body_parts: list[str] = []
    for i, section in enumerate(plan.sections):
        renderer = RENDERERS.get(section.kind)
        if not renderer:
            continue
        if i + 1 < len(plan.sections):
            next_id = plan.sections[i + 1].id
        elif section.kind is SectionKind.SUMMARY:
            next_id = plan.sections[0].id if plan.sections else None
        else:
            next_id = None
        body_parts.append(renderer(plan, section, next_id))

    noscript_facts = extra_noscript or "\n".join(
        f"<li>{_esc(i)}</li>"
        for s in plan.sections
        if s.kind is SectionKind.SUMMARY
        for i in s.items
    )

    fonts = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600;700&family=Manrope:wght@400;600;700&family=Unbounded:wght@500;600;700&display=swap" rel="stylesheet">
""".strip()

    # Fonts from Google are non-critical; content remains readable with fallbacks.
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{_esc(plan.title)}</title>
{fonts}
<style>
{css}
</style>
</head>
<body>
<div class="progress" aria-hidden="true"><span></span></div>
<main>
{''.join(body_parts)}
</main>
<noscript>
  <section class="chapter">
    <div class="wrap">
      <h2>Содержание без JavaScript</h2>
      <ul>{noscript_facts}</ul>
    </div>
  </section>
</noscript>
<script>
{BASE_JS}
</script>
<!-- plan_meta:{_esc(json.dumps({"metaphor": plan.metaphor, "lessons": plan.source_lesson_ids}, ensure_ascii=False))} -->
</body>
</html>
"""
