"""Pre-flight system & dependency auditor (Phase 2 — Production Grade).

Audits ALL required dependencies before booting FastAPI services:
- Python packages (edge_tts, faster_whisper, kokoro, pypdf, openpyxl, ...)
- System binaries (ffmpeg, pandoc, pdftotext)
- Environment keys (OPENROUTER_API_KEY)
- File-system permissions (output/, scratch/, config/)

On failure: logs an explicit diagnostic and raises PreflightError so
startup is hard-blocked (per approved Option 1).
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# import-name -> pip-install hint
REQUIRED_PACKAGES: dict[str, str] = {
    "click": "pip install click>=8.1",
    "yaml": "pip install pyyaml>=6.0",
    "jsonschema": "pip install jsonschema>=4.21",
    "httpx": "pip install httpx>=0.27",
    "PIL": "pip install pillow>=10.0",
    "dotenv": "pip install python-dotenv>=1.0",
    "jinja2": "pip install jinja2>=3.1",
    "playwright": "pip install playwright>=1.44",
    "fastapi": "pip install fastapi>=0.110",
    "uvicorn": "pip install uvicorn>=0.29",
    # Production-grade media/LLM/doc extras (audited, hard-block if missing):
    "edge_tts": "pip install edge-tts",
    "faster_whisper": "pip install faster-whisper",
    "kokoro": "pip install kokoro>=0.9.4",
    "pypdf": "pip install pypdf",
    "openpyxl": "pip install openpyxl",
}

REQUIRED_BINARIES: dict[str, str] = {
    "ffmpeg": "Install ffmpeg and ensure it is on PATH (https://ffmpeg.org/download.html)",
    "pandoc": "Install pandoc and ensure it is on PATH (https://pandoc.org/installing.html)",
    "pdftotext": "Install poppler-utils (provides pdftotext) and ensure it is on PATH",
}

REQUIRED_ENV_KEYS: tuple[str, ...] = ("OPENROUTER_API_KEY",)

REQUIRED_DIRS: tuple[str, ...] = ("output", "scratch", "config")


@dataclass
class PreflightResult:
    ok: bool
    missing_packages: list[str] = field(default_factory=list)
    missing_binaries: list[str] = field(default_factory=list)
    missing_env: list[str] = field(default_factory=list)
    unwritable_dirs: list[str] = field(default_factory=list)

    def diagnostic(self) -> str:
        parts: list[str] = []
        for pkg in self.missing_packages:
            hint = REQUIRED_PACKAGES.get(pkg, f"pip install {pkg}")
            parts.append(f"Missing package '{pkg}'. Run {hint}")
        for binary in self.missing_binaries:
            hint = REQUIRED_BINARIES.get(binary, "")
            parts.append(f"Missing binary '{binary}'. {hint}".strip())
        for key in self.missing_env:
            parts.append(f"Missing environment key '{key}' (set it in .env)")
        for path in self.unwritable_dirs:
            parts.append(f"Directory '{path}' is missing or not writable")
        detail = "; ".join(parts) if parts else "all checks passed"
        return f"❌ Pre-flight Failed: {detail}" if not self.ok else f"✅ Pre-flight OK: {detail}"


class PreflightError(RuntimeError):
    """Raised when pre-flight blocks startup."""


def _package_missing(import_name: str) -> bool:
    return importlib.util.find_spec(import_name) is None


def run_preflight(
    root: str | Path | None = None,
    *,
    strict: bool = True,
    check_packages: bool = True,
    check_binaries: bool = True,
    check_env: bool = True,
    check_dirs: bool = True,
) -> PreflightResult:
    """Run all audits. Returns PreflightResult (ok=True when clean)."""
    base = Path(root) if root is not None else Path.cwd()
    missing_packages = (
        [name for name in REQUIRED_PACKAGES if _package_missing(name)] if check_packages else []
    )
    missing_binaries = (
        [name for name in REQUIRED_BINARIES if shutil.which(name) is None]
        if check_binaries
        else []
    )
    missing_env = (
        [key for key in REQUIRED_ENV_KEYS if not os.environ.get(key, "").strip()]
        if check_env
        else []
    )
    unwritable_dirs: list[str] = []
    if check_dirs:
        for dirname in REQUIRED_DIRS:
            target = base / dirname
            try:
                target.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryFile(dir=str(target)):
                    pass
                if not os.access(str(target), os.W_OK | os.X_OK):
                    unwritable_dirs.append(dirname)
            except Exception:
                unwritable_dirs.append(dirname)

    ok = not (missing_packages or missing_binaries or missing_env or unwritable_dirs)
    result = PreflightResult(
        ok=ok,
        missing_packages=missing_packages,
        missing_binaries=missing_binaries,
        missing_env=missing_env,
        unwritable_dirs=unwritable_dirs,
    )
    if ok:
        logger.info("✅ Pre-flight OK: packages, binaries, env keys, and dirs verified")
    else:
        logger.error(result.diagnostic())
    if not ok and strict:
        raise PreflightError(result.diagnostic())
    return result
