# Architecture

## One lesson → one page

- One `lesson_id` → one standalone HTML document.
- Multiple ids can be merged for experiments; production-style usage is one lesson per page.
- Test steps (`scheme_description.isTest`) are skipped by default.

## Layers

| Layer | Offline | LLM (`--mode llm` / `llm-html`) |
| --- | --- | --- |
| Parse / sanitize / media | yes | yes |
| Fact extraction | yes | yes |
| Lesson plan | templates + heuristics | structured JSON plan |
| HTML | local composer | composer **or** full HTML from the model |
| Coverage / tech report | yes | yes |
| Fallback | — | broken JSON → offline |

## Media resolution

1. `s3_url` when present
2. otherwise `{EDWISE_MEDIA_BASE}/{id}`
3. optional local cache / data-URI embed
4. on failure → placeholder + warning

## HTML safety

- `richText`: sanitize (no script/style/event handlers)
- charts: plaintext summary only
- page JS: no `eval` / `fetch` / outbound XHR patterns (validated)

## Design tokens

`themes.py` picks tokens by domain heuristic.  
Brand overrides come from `style_example.json` via `style_tokens.py`.

## LLM gateway

`POST {EDWISE_GPT_BASE}/request/` with fields:
`key`, `request`, `engine`, `is_json`, `asynchronous` (optional `temperature`).
