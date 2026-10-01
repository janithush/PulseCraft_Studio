"""M4 Local Asset Directory Indexer (`input/visuals/` + `input/audio/`).

Auto-indexes creator-dropped files, extracts lightweight metadata
(dimensions for images, duration/sample-rate for audio), and resolves
`[Visual: name]` / audio tags to on-disk paths (traversal-guarded).
"""

from __future__ import annotations

import logging
import re
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}
AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".m4a", ".flac"}

TAG_WRAPPER_RE = re.compile(r"^\s*\[Visual:\s*(.+?)\s*\]\s*$", re.IGNORECASE)


@dataclass
class LocalAsset:
    """One indexed local file."""

    name: str
    path: Path
    kind: str  # "image" | "video" | "audio"
    size_bytes: int
    width: int | None = None
    height: int | None = None
    duration_sec: float | None = None
    sample_rate_hz: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "kind": self.kind,
            "size_bytes": self.size_bytes,
            "width": self.width,
            "height": self.height,
            "duration_sec": self.duration_sec,
            "sample_rate_hz": self.sample_rate_hz,
            **self.extra,
        }


def _kind_for(suffix: str) -> str | None:
    suffix = suffix.lower()
    if suffix in IMAGE_EXTS:
        return "image"
    if suffix in VIDEO_EXTS:
        return "video"
    if suffix in AUDIO_EXTS:
        return "audio"
    return None


def _image_dims(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(path) as img:
            return img.width, img.height
    except Exception as exc:
        logger.debug("local_mgr image probe failed %s: %s", path, exc)
        return None, None


def _wav_meta(path: Path) -> tuple[float | None, int | None]:
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            if rate:
                return frames / float(rate), int(rate)
    except Exception as exc:
        logger.debug("local_mgr wav probe failed %s: %s", path, exc)
    return None, None


def index_local_assets(
    visuals_dir: str | Path = "input/visuals",
    audio_dir: str | Path = "input/audio",
) -> list[LocalAsset]:
    """Scan both dirs and return sorted asset entries (skips unknown exts)."""
    assets: list[LocalAsset] = []
    for directory in (Path(visuals_dir), Path(audio_dir)):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.name == ".gitkeep":
                continue
            kind = _kind_for(path.suffix)
            if kind is None:
                logger.info("local_mgr skip unsupported %s", path.name)
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            asset = LocalAsset(name=path.name, path=path.resolve(), kind=kind, size_bytes=size)
            if kind == "image":
                asset.width, asset.height = _image_dims(path)
            elif kind == "audio" and path.suffix.lower() == ".wav":
                asset.duration_sec, asset.sample_rate_hz = _wav_meta(path)
            assets.append(asset)
    assets.sort(key=lambda item: item.name.lower())
    logger.info("local_mgr indexed=%d", len(assets))
    return assets


def normalize_tag(tag: str) -> str:
    """Strip `[Visual: ...]` wrappers and directories; basename only."""
    text = (tag or "").strip()
    match = TAG_WRAPPER_RE.match(text)
    if match:
        text = match.group(1).strip().strip("'\"")
    return Path(text).name


def find_for_tag(
    tag: str,
    visuals_dir: str | Path = "input/visuals",
    audio_dir: str | Path = "input/audio",
) -> Path | None:
    """Case-insensitive basename match across both dirs; traversal-guarded."""
    wanted = normalize_tag(tag).lower()
    if not wanted or wanted in {".", ".."}:
        return None
    for directory in (Path(visuals_dir), Path(audio_dir)):
        root = directory.resolve() if directory.exists() else directory
        candidate = (directory / Path(wanted).name).resolve() if directory.exists() else None
        # Direct-hit fast path (traversal-guarded).
        if candidate is not None and root.exists():
            try:
                if root not in candidate.parents and candidate != root:
                    continue
            except Exception:
                continue
            if candidate.is_file() and candidate.name.lower() == wanted:
                return candidate
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.name.lower() == wanted:
                resolved = path.resolve()
                r = directory.resolve()
                if r in resolved.parents or resolved == r:
                    return resolved
    return None
