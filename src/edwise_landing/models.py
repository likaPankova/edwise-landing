from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BlockKind(str, Enum):
    RICH_TEXT = "richText"
    AI_IMG = "aiImg"
    AI_CHART = "aiChart"
    FLIP_CARD = "flipCard"
    AI_GAME = "aiGame"
    ROLE_PLAY = "rolePlay"
    UNKNOWN = "unknown"


class MediaRef(BaseModel):
    media_id: int
    name: str | None = None
    mimetype: str | None = None
    s3_url: str | None = None
    resolved_url: str | None = None
    local_path: str | None = None
    data_uri: str | None = None
    available: bool = False
    warning: str | None = None


class ImgMark(BaseModel):
    object: str | None = None
    description: str | None = None
    mark_title: str | None = None
    x: float | None = None
    y: float | None = None


class FlipSide(BaseModel):
    title: str = ""
    description: str = ""


class FlipCard(BaseModel):
    front: FlipSide
    back: FlipSide


class LessonBlock(BaseModel):
    id: int | str
    kind: BlockKind
    order_num: int = 0
    raw_name: str | None = None
    text_plain: str = ""
    text_html_safe: str = ""
    media_ids: list[int] = Field(default_factory=list)
    media: list[MediaRef] = Field(default_factory=list)
    flip_cards: list[FlipCard] = Field(default_factory=list)
    img_marks: list[ImgMark] = Field(default_factory=list)
    chart_summary: str = ""
    warnings: list[str] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)


class Lesson(BaseModel):
    id: int
    code: str
    description: str = ""
    order_num: int = 0
    is_test: bool = False
    blocks: list[LessonBlock] = Field(default_factory=list)
    media_index: dict[int, MediaRef] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class Fact(BaseModel):
    id: str
    text: str
    category: str = "general"
    required: bool = True
    source: str = ""


class SectionKind(str, Enum):
    HERO = "hero"
    GOALS = "goals"
    PROSE = "prose"
    DEFINITION = "definition"
    WARNING = "warning"
    TIMELINE = "timeline"
    CHECKLIST = "checklist"
    CARDS = "cards"
    FLIP = "flip"
    QUIZ = "quiz"
    MEDIA = "media"
    PRACTICE = "practice"
    SUMMARY = "summary"


class PlanSection(BaseModel):
    id: str
    kind: SectionKind
    title: str
    lead: str = ""
    body: str = ""
    items: list[str] = Field(default_factory=list)
    pairs: list[dict[str, str]] = Field(default_factory=list)
    quiz: list[dict[str, Any]] = Field(default_factory=list)
    media: list[MediaRef] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)


class ThemeTokens(BaseModel):
    metaphor: str
    ink: str
    paper: str
    accent: str
    accent_2: str
    dark: str
    warning: str
    font_display: str
    font_body: str


class LessonPlan(BaseModel):
    title: str
    subtitle: str = ""
    metaphor: str = ""
    theme: ThemeTokens
    learning_goals: list[str] = Field(default_factory=list)
    sections: list[PlanSection] = Field(default_factory=list)
    must_cover_fact_ids: list[str] = Field(default_factory=list)
    source_lesson_ids: list[int] = Field(default_factory=list)


class CoverageItem(BaseModel):
    fact_id: str
    text: str
    present: bool
    evidence: str = ""


class CoverageReport(BaseModel):
    total: int
    covered: int
    missing: list[CoverageItem] = Field(default_factory=list)
    items: list[CoverageItem] = Field(default_factory=list)


class TechIssue(BaseModel):
    severity: str
    code: str
    message: str


class TechReport(BaseModel):
    ok: bool
    issues: list[TechIssue] = Field(default_factory=list)


class RunReport(BaseModel):
    mode: str
    lesson_ids: list[int]
    warnings: list[str] = Field(default_factory=list)
    coverage: CoverageReport
    tech: TechReport
    llm_calls: list[dict[str, Any]] = Field(default_factory=list)
    timing: dict[str, float] = Field(default_factory=dict)
    output_html: str = ""
    output_report: str = ""
