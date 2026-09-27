# Lesson landing page generator

Pipeline that turns structured lesson JSON into a **standalone interactive HTML page**
(CSS + JS inline): hero, facts, flip cards, quizzes, media placeholders, tech validation.

Built as a portfolio / R&D prototype for educational content packaging.

## Features

- Parse & sanitize lesson blocks (`richText`, `aiImg`, `flipCard`, charts, games, …)
- Fact extraction + coverage-oriented planning
- Two generation modes:
  - **offline** — deterministic local HTML composition
  - **llm-html** — model returns a full HTML document (with style continuity hooks)
- Optional hero image via a media-generation HTTP API
- Technical HTML validation (DOCTYPE, landmarks, unsafe JS patterns)
- CLI for local runs

## Project layout

```text
src/edwise_landing/   # pipeline package
data/                 # sample course JSON (anonymized)
docs/                 # architecture notes
tests/                # smoke tests
style_example.json    # demo brand tokens
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# put your GPT key into .env if you want LLM mode
```

## Run (offline, no API keys)

```bash
python -m edwise_landing generate \
  --course data/sample_course.json \
  --lesson 1001 \
  --mode offline \
  --tag demo
```

Output goes to `outputs/`.

## Run (LLM HTML)

Requires a GPT-service compatible HTTP API (see `.env.example`).

```bash
export EDWISE_GPT_ENGINE=gpt-5.6-luna

python -m edwise_landing generate \
  --course data/sample_course.json \
  --lesson 1001 \
  --mode llm-html \
  --tag review
```

## Tests

```bash
pytest -q
```

## Notes

- This repository is a **cleaned public snapshot** of a private R&D prototype.
- Company-specific course data, brand packs, and production service code are **not** included.
- Default service URLs in the code are placeholders — configure via environment variables.

## License

MIT
