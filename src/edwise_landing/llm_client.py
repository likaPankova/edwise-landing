from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


DEFAULT_BASE = "https://your-gpt-service.example.com/gpt-service/api/v1"
DEFAULT_HOST = "https://your-gpt-service.example.com"


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


def _normalize_base(url: str) -> str:
    """Accept host or full API root from other projects."""
    url = (url or DEFAULT_BASE).rstrip("/")
    if url.endswith("/gpt-service/api/v1"):
        return url
    if url.endswith("/api/v1"):
        return url
    # bare host like https://your-gpt-service.example.com
    return f"{url}/gpt-service/api/v1"


@dataclass
class LLMCallLog:
    engine: str
    prompt_chars: int
    answer_chars: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    duration_sec: float = 0.0
    request_id: int | None = None
    ok: bool = True
    error: str | None = None


@dataclass
class GPTServiceClient:
    api_key: str
    base_url: str = DEFAULT_BASE
    default_engine: str = "gpt-5.6-luna"
    auth_token: str | None = None
    timeout: float = 180.0
    poll_interval: float = 5.0
    max_polls: int = 240
    logs: list[LLMCallLog] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "GPTServiceClient | None":
        key = _first_env("EDWISE_GPT_KEY", "GPT_SERVICE_KEY")
        if not key:
            return None

        poll_ms = _first_env("GPT_POLL_DELAY_MS", "EDWISE_GPT_POLL_MS", default="5000")
        max_polls = _first_env("GPT_MAX_POLLS", "EDWISE_GPT_MAX_POLLS", default="240")
        try:
            poll_interval = max(0.5, float(poll_ms) / 1000.0)
        except ValueError:
            poll_interval = 5.0
        try:
            max_polls_i = max(1, int(max_polls))
        except ValueError:
            max_polls_i = 240

        # Task brief prefers luna for simple structured steps; fall back to project engine.
        engine = _first_env(
            "EDWISE_GPT_ENGINE",
            "GPT_SERVICE_ENGINE",
            default="gpt-5.6-luna",
        )
        # Prefer assignment-allowed engines when project default is outside brief.
        if engine.startswith("gpt-5.2") or engine == "sonar-deep-research":
            engine = _first_env("EDWISE_GPT_ENGINE", default="gpt-5.6-luna")

        return cls(
            api_key=key,
            base_url=_normalize_base(
                _first_env("EDWISE_GPT_BASE", "GPT_SERVICE_BASE_URL", default=DEFAULT_HOST)
            ),
            default_engine=engine,
            auth_token=_first_env("EDWISE_GPT_AUTH_TOKEN", "GPT_SERVICE_AUTH_TOKEN") or None,
            poll_interval=poll_interval,
            max_polls=max_polls_i,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def complete(
        self,
        prompt: str,
        *,
        engine: str | None = None,
        is_json: bool = True,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        asynchronous: bool = False,
    ) -> str:
        engine = engine or self.default_engine
        if engine == "claude-sonnet-5" and is_json:
            # assignment constraint
            is_json = False

        # Dev gpt-service currently fails when max_tokens is set; omit by default.
        # Claude on this gateway also fails when temperature is sent.
        payload: dict[str, Any] = {
            "key": self.api_key,
            "request": prompt,
            "engine": engine,
            "is_json": is_json,
            "asynchronous": asynchronous,
        }
        if engine != "claude-sonnet-5":
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        started = time.perf_counter()
        log = LLMCallLog(engine=engine, prompt_chars=len(prompt), answer_chars=0)
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.post(
                    f"{self.base_url}/request/",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                req_id = data.get("id")
                log.request_id = req_id
                answer = data.get("answer") or ""
                if asynchronous or data.get("is_processing"):
                    answer = self._poll(client, req_id)
                log.prompt_tokens = data.get("prompt_tokens")
                log.completion_tokens = data.get("completion_tokens")
                log.total_tokens = data.get("total_tokens")
                if req_id:
                    detail = client.get(
                        f"{self.base_url}/request/{req_id}/",
                        headers=self._headers(),
                    ).json()
                    log.prompt_tokens = detail.get("prompt_tokens", log.prompt_tokens)
                    log.completion_tokens = detail.get(
                        "completion_tokens", log.completion_tokens
                    )
                    log.total_tokens = detail.get("total_tokens", log.total_tokens)
                    if detail.get("is_failed"):
                        raise RuntimeError(f"LLM request failed: {detail.get('answer')}")
                    answer = detail.get("answer") or answer
                log.answer_chars = len(answer or "")
                log.ok = True
                return answer or ""
        except Exception as exc:  # noqa: BLE001
            log.ok = False
            log.error = str(exc)
            raise
        finally:
            log.duration_sec = time.perf_counter() - started
            self.logs.append(log)

    def _poll(self, client: httpx.Client, req_id: int) -> str:
        for _ in range(self.max_polls):
            detail = client.get(
                f"{self.base_url}/request/{req_id}/",
                headers=self._headers(),
            ).json()
            if detail.get("is_completed"):
                return detail.get("answer") or ""
            if detail.get("is_failed") or detail.get("is_cancelled"):
                raise RuntimeError(f"LLM request ended: {detail}")
            time.sleep(self.poll_interval)
        raise TimeoutError(f"LLM request {req_id} timed out after {self.max_polls} polls")
