"""SFX (Freesound CC0) + BGM (Pixabay Audio) fetcher (M3).

Keyless providers return [] (treated as disabled with a warning upstream).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any


def fetch_freesound_sfx(tag: str, timeout_s: float = 15.0) -> list[dict[str, Any]]:
    """Freesound CC0 search → [{url, name, license, provider}]."""
    import httpx

    token = os.environ.get("FREESOUND_API_KEY", "")
    if not token:
        return []
    with httpx.Client(timeout=timeout_s) as client:
        resp = client.get(
            "https://freesound.org/apiv2/search/text/",
            params={
                "query": tag,
                "filter": "license:Creative Commons 0",
                "fields": "id,name,previews,license",
            },
            headers={"Authorization": f"Token {token}"},
        )
        resp.raise_for_status()
        data = resp.json()
    return [
        {
            "url": (hit.get("previews") or {}).get("preview-hq-mp3", ""),
            "name": hit.get("name", tag),
            "license": hit.get("license", "https://creativecommons.org/publicdomain/zero/1.0/"),
            "provider": "freesound",
        }
        for hit in data.get("results", [])
    ]


def fetch_pixabay_bgm(tag: str, timeout_s: float = 15.0) -> list[dict[str, Any]]:
    """Pixabay audio search → [{url, name, license, provider}]."""
    import httpx

    key = os.environ.get("PIXABAY_API_KEY", "")
    if not key:
        return []
    with httpx.Client(timeout=timeout_s) as client:
        resp = client.get(
            "https://pixabay.com/api/videos/",
            params={"key": key, "q": tag, "per_page": 3},
        )
        if resp.status_code != 200:
            resp = client.get(
                "https://pixabay.com/api/", params={"key": key, "q": f"{tag} music", "per_page": 3}
            )
            resp.raise_for_status()
        data = resp.json()
    return [
        {
            "url": hit.get("previewURL", hit.get("pageURL", "")),
            "name": hit.get("tags", tag),
            "license": "https://pixabay.com/service/license/",
            "provider": "pixabay-audio",
        }
        for hit in data.get("hits", [])
    ]


class AudioFetcher:
    """Tag-driven SFX/BGM fetch with content-addressed download paths."""

    def __init__(self, cache_dir: str | Path = ".cache/audio", flags: Any = None) -> None:
        self._cache = Path(cache_dir)
        self._flags = flags

    def _on(self, dotted: str) -> bool:
        if self._flags is None:
            return True
        try:
            return bool(self._flags.enabled(dotted))
        except Exception:
            return True

    def fetch(self, tags: list[str], kind: str = "bgm") -> tuple[list[dict[str, Any]], list[str]]:
        """Returns (hits, warnings) for `kind` in {"sfx", "bgm"}."""
        toggle = f"audio.{kind}"
        if not self._on(toggle):
            return [], [f"toggle '{toggle}' disabled: skipping {kind.upper()} fetch"]
        warnings: list[str] = []
        hits: list[dict[str, Any]] = []
        for tag in tags or []:
            try:
                found = fetch_freesound_sfx(tag) if kind == "sfx" else fetch_pixabay_bgm(tag)
            except Exception as exc:
                warnings.append(f"{kind} fetch for '{tag}' failed ({exc})")
                continue
            if not found:
                warnings.append(f"{kind} fetch for '{tag}': no results (key missing?)")
                continue
            hit = found[0]
            hit["localPath"] = self._cached_path(kind, tag, hit["url"])
            hits.append(hit)
        return hits, warnings

    def _cached_path(self, kind: str, tag: str, url: str) -> str:
        digest = hashlib.sha256(f"{kind}|{tag}|{url}".encode()).hexdigest()[:12]
        return str(self._cache / kind / digest)
