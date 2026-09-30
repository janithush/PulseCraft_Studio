"""Multi-source B-roll fetcher + local overrides (M3).

Order: local `input/visuals/` tags → Pexels → Pixabay → Openverse → fallback.
Providers without keys are skipped (warning); nothing here hard-fails.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

VISUAL_TAG_RE = re.compile(r"\[Visual:\s*([^\]]+)\]", re.IGNORECASE)


class MediaError(RuntimeError):
    """All providers failed and no fallback was permitted."""


def extract_visual_tags(script: str) -> list[str]:
    """Parse `[Visual: file-or-query]` tags from script text."""
    return [match.strip() for match in VISUAL_TAG_RE.findall(script or "")]


def resolve_local_override(tag: str, visuals_dir: str | Path = "input/visuals") -> Path | None:
    """Return the local file for a tag, or None. Traversal-guarded."""
    root = Path(visuals_dir).resolve()
    candidate = (root / Path(tag).name).resolve()
    if root not in candidate.parents and candidate != root:
        return None
    return candidate if candidate.is_file() else None


def _get(url: str, headers: dict[str, str], timeout_s: float = 15.0) -> Any:
    import httpx

    with httpx.Client(timeout=timeout_s) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


def fetch_pexels(
    query: str, orientation: str = "portrait", per_page: int = 3
) -> list[dict[str, Any]]:
    """Pexels image/video search → [{url, photographer, license, provider}]."""
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        return []
    data = _get(
        f"https://api.pexels.com/v1/search?query={query}&orientation={orientation}&per_page={per_page}",
        {"Authorization": key},
    )
    return [
        {
            "url": photo["src"].get("large2x", photo["src"].get("original")),
            "photographer": photo.get("photographer", "unknown"),
            "license": photo.get("url", "https://www.pexels.com/license/"),
            "provider": "pexels",
        }
        for photo in data.get("photos", [])
    ]


def fetch_pixabay(query: str, media_type: str = "photo") -> list[dict[str, Any]]:
    """Pixabay image/video search (keyed)."""
    key = os.environ.get("PIXABAY_API_KEY", "")
    if not key:
        return []
    data = _get(
        f"https://pixabay.com/api/?key={key}&q={query}&image_type={media_type}&per_page=3",
        {},
    )
    return [
        {
            "url": hit.get("largeImageURL", hit.get("pageURL")),
            "photographer": hit.get("user", "unknown"),
            "license": "https://pixabay.com/service/license/",
            "provider": "pixabay",
        }
        for hit in data.get("hits", [])
    ]


def fetch_openverse(query: str) -> list[dict[str, Any]]:
    """Openverse CC search (keyless)."""
    try:
        data = _get(f"https://api.openverse.org/v1/images/?q={query}&page_size=3", {})
    except Exception:
        return []
    return [
        {
            "url": item.get("url"),
            "photographer": item.get("creator", "unknown"),
            "license": item.get("license_url", item.get("license", "unknown")),
            "provider": "openverse",
        }
        for item in data.get("results", [])
        if item.get("url")
    ]


class MediaFetcher:
    """Ordered providers with local-override short-circuit + manifest log."""

    def __init__(
        self,
        cache_dir: str | Path = ".cache/media",
        visuals_dir: str | Path = "input/visuals",
        flags: Any = None,
    ) -> None:
        self._cache = Path(cache_dir)
        self._visuals = Path(visuals_dir)
        self._flags = flags

    def _provider_on(self, name: str) -> bool:
        if self._flags is None:
            return True
        try:
            return bool(self._flags.enabled(f"media.{name}"))
        except Exception:
            return True

    def fetch_scene(
        self, query: str, orientation: str = "portrait", strict: bool = False
    ) -> tuple[dict[str, Any], list[str]]:
        """Returns (asset, warnings). Local tags win; providers cascade."""
        warnings: list[str] = []
        local = (
            resolve_local_override(query, self._visuals)
            if self._flags is None or self._guard_local()
            else None
        )
        if local is not None:
            return {
                "url": local.as_uri(),
                "localPath": str(local),
                "provider": "local",
                "photographer": "local",
                "license": "local",
            }, warnings
        providers = (
            ("pexels", lambda: fetch_pexels(query, orientation)),
            ("pixabay", lambda: fetch_pixabay(query)),
            ("openverse", lambda: fetch_openverse(query)),
        )
        for name, call in providers:
            if not self._provider_on(name):
                warnings.append(f"toggle 'media.{name}' disabled: skipping provider")
                continue
            try:
                hits = call()
            except Exception as exc:
                warnings.append(f"{name} failed ({exc}); trying next provider")
                continue
            if hits:
                asset = hits[0]
                asset["localPath"] = self._cached_path(name, query, asset["url"])
                return asset, warnings
            warnings.append(f"{name}: no results for '{query}'")
        if strict:
            raise MediaError(f"all media providers failed for '{query}'")
        warnings.append(f"all providers empty for '{query}'; using bundled fallback")
        return {
            "url": "",
            "localPath": "",
            "provider": "fallback",
            "photographer": "",
            "license": "",
        }, warnings

    def _guard_local(self) -> bool:
        try:
            return bool(self._flags.enabled("media.localOverrides"))
        except Exception:
            return True

    def _cached_path(self, provider: str, query: str, url: str) -> str:
        digest = hashlib.sha256(f"{provider}|{query}|{url}".encode()).hexdigest()[:12]
        return str(self._cache / provider / digest)

    def write_manifest(self, assets: list[dict[str, Any]], out_path: str | Path) -> Path:
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(assets, indent=2), encoding="utf-8")
        return target
