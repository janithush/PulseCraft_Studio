"""M4 Asset Caching Engine: disk-backed, hash-indexed cache (`.cache/assets/`).

Covers media + audio bytes fetched from Pexels, Pixabay, Freesound, Openverse.
Identical (provider, query, url) tuples share one on-disk entry, so repeat
runs perform zero duplicate network requests. Hits/misses are logged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

INDEX_FILENAME = "index.json"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024 * 1024  # 5GB LRU budget (ARCH §4.7)


def cache_key(provider: str, query: str, url: str) -> str:
    """Stable 16-hex-char key for a (provider, query, url) triple."""
    raw = f"{provider}|{query}|{url}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


class AssetCache:
    """Content-addressed disk cache with a JSON hash index.

    Layout: `.cache/assets/<provider>/<key><ext>` + `.cache/assets/index.json`
    mapping `key -> {provider, query, url, path, size_bytes, sha256, fetched_at}`.
    """

    def __init__(self, cache_dir: str | Path = ".cache/assets") -> None:
        self._root = Path(cache_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        self._index_path = self._root / INDEX_FILENAME

    # -- core API --------------------------------------------------------
    def path_for(self, provider: str, query: str, url: str) -> Path:
        """Deterministic on-disk path for a triple (does not touch disk)."""
        key = cache_key(provider, query, url)
        suffix = Path(url.split("?")[0]).suffix or ".bin"
        if len(suffix) > 8:
            suffix = ".bin"
        return self._root / provider / f"{key}{suffix}"

    def get(self, provider: str, query: str, url: str) -> Path | None:
        """Return the cached path on hit, else None. Logs hit/miss."""
        target = self.path_for(provider, query, url)
        if target.is_file():
            logger.info(
                "assets.cache hit provider=%s key=%s",
                provider,
                target.stem,
            )
            return target
        logger.info("assets.cache miss provider=%s key=%s", provider, target.stem)
        return None

    def put(self, provider: str, query: str, url: str, data: bytes) -> Path:
        """Store bytes atomically and update the hash index. Returns path."""
        target = self.path_for(provider, query, url)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
        digest = hashlib.sha256(data).hexdigest()
        self._update_index(
            cache_key(provider, query, url),
            {
                "provider": provider,
                "query": query,
                "url": url,
                "path": str(target),
                "size_bytes": len(data),
                "sha256": digest,
                "fetched_at": time.time(),
            },
        )
        logger.info(
            "assets.cache store provider=%s key=%s bytes=%d", provider, target.stem, len(data)
        )
        return target

    def fetch_or_download(
        self,
        provider: str,
        query: str,
        url: str,
        downloader: Callable[[], bytes],
    ) -> Path:
        """Return cached bytes or call `downloader()` exactly once on miss."""
        hit = self.get(provider, query, url)
        if hit is not None:
            self._touch(cache_key(provider, query, url))
            return hit
        return self.put(provider, query, url, downloader())

    # -- introspection / eviction ----------------------------------------
    def list_cached(self) -> list[dict[str, Any]]:
        """Return hash-index rows; rebuilds the index if it is corrupt."""
        index = self._load_index()
        rows: list[dict[str, Any]] = []
        for key, entry in sorted(index.items()):
            path = Path(str(entry.get("path", "")))
            if path.is_file():
                rows.append({"key": key, **entry})
        return rows

    def clear(self) -> int:
        """Delete the whole `.cache/assets/` tree. Returns asset files removed."""
        count = len(self.list_cached())
        if self._root.is_dir():
            shutil.rmtree(self._root, ignore_errors=True)
        self._root.mkdir(parents=True, exist_ok=True)
        self._write_index({})
        logger.info("assets.cache cleared files=%d", count)
        return count

    def evict_lru(self, max_bytes: int = DEFAULT_MAX_BYTES) -> int:
        """Drop oldest `fetched_at` entries until under budget. Returns evicted count."""
        rows = self.list_cached()
        total = sum(int(row.get("size_bytes", 0)) for row in rows)
        if total <= max_bytes:
            return 0
        by_age = sorted(rows, key=lambda row: float(row.get("fetched_at", 0.0)))
        index = self._load_index()
        evicted = 0
        for row in by_age:
            if total <= max_bytes:
                break
            path = Path(str(row["path"]))
            try:
                if path.is_file():
                    total -= path.stat().st_size
                    path.unlink()
            except OSError:
                continue
            index.pop(str(row["key"]), None)
            evicted += 1
        self._write_index(index)
        logger.info("assets.cache evict_lru evicted=%d", evicted)
        return evicted

    # -- index helpers ----------------------------------------------------
    def _load_index(self) -> dict[str, Any]:
        if not self._index_path.is_file():
            return {}
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return self._rebuild_index()
        return raw if isinstance(raw, dict) else {}

    def _write_index(self, index: dict[str, Any]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    def _update_index(self, key: str, entry: dict[str, Any]) -> None:
        index = self._load_index()
        index[key] = entry
        self._write_index(index)

    def _touch(self, key: str) -> None:
        index = self._load_index()
        if key in index:
            index[key]["fetched_at"] = time.time()
            self._write_index(index)

    def _rebuild_index(self) -> dict[str, Any]:
        rebuilt: dict[str, Any] = {}
        for path in sorted(self._root.rglob("*")):
            if path.is_file() and path.name != INDEX_FILENAME:
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                rebuilt[path.stem] = {
                    "provider": path.parent.name,
                    "query": "",
                    "url": "",
                    "path": str(path),
                    "size_bytes": size,
                    "sha256": "",
                    "fetched_at": path.stat().st_mtime,
                }
        self._write_index(rebuilt)
        return rebuilt
