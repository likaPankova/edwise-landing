from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import httpx

from .models import Lesson, MediaRef


DEFAULT_MEDIA_BASE = "https://your-backend.example.com/api/media2"


class MediaResolver:
    def __init__(
        self,
        *,
        media_base: str = DEFAULT_MEDIA_BASE,
        cache_dir: str | Path = "assets_cache",
        embed: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self.media_base = media_base.rstrip("/")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.embed = embed
        self.timeout = timeout
        self.warnings: list[str] = []

    def public_url(self, media_id: int) -> str:
        return f"{self.media_base}/{media_id}"

    def resolve_ref(self, ref: MediaRef, client: httpx.Client | None = None) -> MediaRef:
        out = ref.model_copy(deep=True)
        candidates: list[str] = []
        if out.s3_url:
            candidates.append(out.s3_url)
        candidates.append(self.public_url(out.media_id))

        own_client = client is None
        client = client or httpx.Client(timeout=self.timeout, follow_redirects=True)
        try:
            for url in candidates:
                try:
                    resp = client.get(url)
                    if resp.status_code != 200 or not resp.content:
                        continue
                    ctype = resp.headers.get("content-type", out.mimetype or "application/octet-stream")
                    ext = mimetypes.guess_extension(ctype.split(";")[0].strip()) or ".bin"
                    local = self.cache_dir / f"{out.media_id}{ext}"
                    local.write_bytes(resp.content)
                    out.resolved_url = url
                    out.local_path = str(local)
                    out.mimetype = ctype.split(";")[0].strip()
                    out.available = True
                    out.warning = None
                    if self.embed and out.mimetype.startswith(("image/", "audio/", "video/")):
                        b64 = base64.b64encode(resp.content).decode("ascii")
                        out.data_uri = f"data:{out.mimetype};base64,{b64}"
                    return out
                except httpx.HTTPError as exc:
                    last_err = str(exc)
                    continue
            out.available = False
            out.resolved_url = self.public_url(out.media_id)
            out.warning = "media_download_failed"
            self.warnings.append(f"media_download_failed:{out.media_id}")
            return out
        finally:
            if own_client:
                client.close()

    def resolve_lesson(self, lesson: Lesson) -> Lesson:
        updated = lesson.model_copy(deep=True)
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            for mid, ref in list(updated.media_index.items()):
                updated.media_index[mid] = self.resolve_ref(ref, client)
            for block in updated.blocks:
                block.media = [
                    updated.media_index.get(m.media_id, self.resolve_ref(m, client))
                    for m in block.media
                ]
                for m in block.media:
                    if not m.available:
                        block.warnings.append(f"media_unavailable:{m.media_id}")
                        self.warnings.append(f"media_unavailable:{m.media_id}")
        updated.warnings.extend(self.warnings)
        return updated
