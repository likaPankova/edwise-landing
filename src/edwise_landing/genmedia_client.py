from __future__ import annotations

import base64
import mimetypes
import os
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx


Orientation = Literal["square", "story", "landscape"]


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


def _normalize_base(url: str) -> str:
    url = (url or "").rstrip("/")
    if url.endswith("/api"):
        return url[: -len("/api")]
    return url


@dataclass
class GenMediaImageResult:
    task_id: int
    engine: str
    prompt: str
    raw_preview_url: str
    data_uri: str | None = None
    ok: bool = True
    error: str | None = None


@dataclass
class GenMediaClient:
    base_url: str
    photo_engine: str
    poll_interval_ms: float = 2000.0
    max_wait_ms: float = 120000.0
    timeout: float = 60.0

    @classmethod
    def from_env(cls) -> "GenMediaClient | None":
        base = _normalize_base(
            _first_env(
                "MEDIA_SERVICE_BASE_URL",
                "EDWISE_GENMEDIA_BASE",
                default="https://your-genmedia-service.example.com",
            )
        )
        engine = _first_env("MEDIA_PHOTO_ENGINE", "EDWISE_GENMEDIA_ENGINE", default="geminipro3")
        if not base:
            return None
        try:
            poll_ms = float(_first_env("MEDIA_POLL_INTERVAL_MS", "EDWISE_GENMEDIA_POLL_MS", default="2000"))
        except ValueError:
            poll_ms = 2000.0
        try:
            max_wait = float(_first_env("MEDIA_MAX_WAIT_MS", "EDWISE_GENMEDIA_MAX_WAIT_MS", default="120000"))
        except ValueError:
            max_wait = 120000.0
        return cls(
            base_url=base,
            photo_engine=engine,
            poll_interval_ms=max(500.0, poll_ms),
            max_wait_ms=max(5000.0, max_wait),
        )

    def _landscape_size(self, engine: str) -> tuple[int, int]:
        if engine in {"flux", "flux_max"}:
            return 1280, 720
        if engine == "geminipro3":
            return 1376, 768
        return 1920, 1080

    def generate_image(
        self,
        prompt: str,
        *,
        engine: str | None = None,
        orientation: Orientation = "landscape",
    ) -> GenMediaImageResult:
        engine = (engine or self.photo_engine).strip()
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("GenMedia prompt is empty")

        if orientation == "landscape":
            width, height = self._landscape_size(engine)
        elif orientation == "story":
            width, height = (768, 1376) if engine == "geminipro3" else (1080, 1920)
        else:
            width, height = 1024, 1024

        payload = {
            "type": "image",
            "engine": engine,
            "request": prompt,
            "asynchronous": True,
            "settings": {"width": width, "height": height},
        }
        create_url = f"{self.base_url}/api/request/"
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            resp = client.post(
                create_url,
                json=payload,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            body = resp.json()
            if not body.get("status") or not body.get("data", {}).get("task_id"):
                raise RuntimeError(f"GenMedia create failed: {body}")
            task_id = int(body["data"]["task_id"])
            engine = body["data"].get("engine") or engine

            started = time.perf_counter()
            while True:
                if (time.perf_counter() - started) * 1000 > self.max_wait_ms:
                    raise TimeoutError(f"GenMedia timeout task_id={task_id}")

                status_url = f"{self.base_url}/api/task-status/{task_id}/"
                st_resp = client.get(status_url, headers={"Accept": "application/json"})
                st_resp.raise_for_status()
                st = st_resp.json()
                data = st.get("data") or {}
                status = data.get("status")
                if status == "FAILED":
                    err = data.get("error") or data.get("response", {}).get("error") or "unknown"
                    raise RuntimeError(f"GenMedia FAILED task_id={task_id}: {err}")
                if status == "COMPLETED":
                    raw = (data.get("response") or {}).get("raw_preview")
                    if not raw:
                        raise RuntimeError(f"GenMedia COMPLETED without raw_preview task_id={task_id}")
                    data_uri = self._fetch_data_uri(client, raw)
                    return GenMediaImageResult(
                        task_id=task_id,
                        engine=engine,
                        prompt=prompt,
                        raw_preview_url=raw,
                        data_uri=data_uri,
                        ok=True,
                    )
                time.sleep(self.poll_interval_ms / 1000.0)

    def _fetch_data_uri(self, client: httpx.Client, url: str) -> str | None:
        try:
            r = client.get(url, timeout=90.0)
            r.raise_for_status()
            mime = r.headers.get("content-type", "").split(";")[0].strip()
            if not mime or mime == "application/octet-stream":
                mime = mimetypes.guess_type(url)[0] or "image/png"
            encoded = base64.b64encode(r.content).decode("ascii")
            return f"data:{mime};base64,{encoded}"
        except Exception:
            return None
