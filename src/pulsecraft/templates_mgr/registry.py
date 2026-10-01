"""M4 Unified Template Manager Registry (posts + reels).

Single interface over `templates/posts/` (Static Post, HTML/Jinja2) and
`templates/reels/` (Video Reel, Remotion React) with strict `meta.json`
JSON-schema validation. Exposes:
`list_all_templates()`, `get_template_schema(name)`, `validate_all_templates()`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REMOTE_URL_RE = re.compile(r"https?://", re.IGNORECASE)
CANVAS_RE = re.compile(r"^\d+x\d+$")

POST_MANIFEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "layoutId",
        "displayName",
        "version",
        "engine",
        "supportedCanvas",
        "safeAreas",
        "placeholders",
    ],
    "properties": {
        "layoutId": {"type": "string", "minLength": 1},
        "displayName": {"type": "string", "minLength": 1},
        "version": {"type": "string", "minLength": 1},
        "engine": {"const": "jinja2"},
        "supportedCanvas": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "safeAreas": {"type": "object"},
        "placeholders": {
            "type": "object",
            "required": ["required", "optional"],
            "properties": {
                "required": {"type": "array", "items": {"type": "string"}},
                "optional": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}

REEL_MANIFEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["themeId", "displayName", "version", "fps"],
    "properties": {
        "themeId": {"type": "string", "minLength": 1},
        "displayName": {"type": "string", "minLength": 1},
        "version": {"type": "string", "minLength": 1},
        "fps": {"type": "integer", "minimum": 1},
        "size": {"type": "string"},
        "sizes": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "tweaks": {"type": "array", "items": {"type": "string"}},
    },
}


class RegistryError(ValueError):
    """Unknown template name or invalid registry state."""


@dataclass
class TemplateEntry:
    name: str
    kind: str  # "post" | "reel"
    path: Path
    meta: dict[str, Any] = field(default_factory=dict)


def _validate_schema(meta: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    try:
        import jsonschema

        jsonschema.validate(instance=meta, schema=schema)
        return []
    except ImportError:
        return _fallback_validate(meta, schema)
    except Exception as exc:
        return [f"meta.json invalid: {exc}"]


def _fallback_validate(meta: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in schema.get("required", []):
        if key not in meta:
            errors.append(f"meta.json invalid: '{key}' is required")
    props = schema.get("properties", {})
    for key, spec in props.items():
        if key in meta and "const" in spec and meta[key] != spec["const"]:
            errors.append(f"meta.json invalid: '{key}' must be '{spec['const']}'")
    return errors


class UnifiedTemplateRegistry:
    """Unified posts + reels registry with strict manifest validation."""

    def __init__(self, root: str | Path = "templates") -> None:
        self._root = Path(root)

    def list_all_templates(self) -> list[TemplateEntry]:
        """Scan posts + reels dirs; sorted by (kind, name)."""
        entries: list[TemplateEntry] = []
        for dirname, kind in (("posts", "post"), ("reels", "reel")):
            kind_dir = self._root / dirname
            if not kind_dir.is_dir():
                continue
            for child in sorted(kind_dir.iterdir()):
                if child.is_dir() and (child / "meta.json").is_file():
                    entries.append(self._describe(kind, child))
        entries.sort(key=lambda entry: (entry.kind, entry.name))
        return entries

    def get_template_schema(self, name: str) -> dict[str, Any]:
        """Return manifest + placeholder schema for a template by name."""
        matches = [entry for entry in self.list_all_templates() if entry.name == name]
        if not matches:
            available = [entry.name for entry in self.list_all_templates()] or "none"
            raise RegistryError(f"unknown template '{name}'. Available: {available}")
        entry = sorted(matches, key=lambda e: 0 if e.kind == "post" else 1)[0]
        placeholders: dict[str, list[str]] = {"required": [], "optional": []}
        raw = entry.meta.get("placeholders")
        if isinstance(raw, dict):
            placeholders = {
                "required": sorted(str(v) for v in raw.get("required", [])),
                "optional": sorted(str(v) for v in raw.get("optional", [])),
            }
        elif entry.kind == "reel":
            tweaks = entry.meta.get("tweaks", [])
            placeholders = {
                "required": ["script", "scenes"],
                "optional": sorted([str(t) for t in tweaks] + ["brandTokens", "presetTweaks"]),
            }
        return {
            "name": entry.name,
            "kind": entry.kind,
            "manifest": dict(entry.meta),
            "placeholders": placeholders,
        }

    def validate_all_templates(self) -> dict[str, list[str]]:
        """Strict-validate every pack. Clean pack maps to []."""
        results: dict[str, list[str]] = {}
        for entry in self.list_all_templates():
            key = f"{entry.kind}s/{entry.name}"
            results[key] = self._validate_entry(entry)
        return results

    # -- internals -------------------------------------------------------
    def _describe(self, kind: str, path: Path) -> TemplateEntry:
        meta: dict[str, Any] = {}
        try:
            meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            meta = {}
        return TemplateEntry(name=path.name, kind=kind, path=path, meta=meta)

    def _validate_entry(self, entry: TemplateEntry) -> list[str]:
        warnings: list[str] = []
        meta_path = entry.path / "meta.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return [f"{entry.name}: meta.json invalid JSON: {exc}"]
        except OSError as exc:
            return [f"{entry.name}: meta.json unreadable: {exc}"]
        schema = POST_MANIFEST_SCHEMA if entry.kind == "post" else REEL_MANIFEST_SCHEMA
        for problem in _validate_schema(meta, schema):
            warnings.append(f"{entry.name}: {problem}")
        if entry.kind == "post":
            if meta.get("layoutId") != entry.name:
                warnings.append(f"{entry.name}: layoutId must equal directory name")
            for asset in ("index.html", "style.css"):
                asset_path = entry.path / asset
                if not asset_path.is_file():
                    warnings.append(f"{entry.name}: missing {asset}")
                elif REMOTE_URL_RE.search(asset_path.read_text(encoding="utf-8")):
                    warnings.append(f"{entry.name}: {asset} references a remote URL")
            for canvas in meta.get("supportedCanvas", []):
                if not CANVAS_RE.match(str(canvas)):
                    warnings.append(f"{entry.name}: bad canvas '{canvas}' (want WxH)")
        else:
            if meta.get("themeId") != entry.name:
                warnings.append(f"{entry.name}: themeId must equal directory name")
            sizes = meta.get("sizes", [meta.get("size")] if meta.get("size") else [])
            if not sizes:
                warnings.append(f"{entry.name}: reel meta needs 'size' or 'sizes[]'")
            for canvas in sizes:
                if not CANVAS_RE.match(str(canvas)):
                    warnings.append(f"{entry.name}: bad size '{canvas}' (want WxH)")
            for asset in ("ReelComposition.tsx", "theme.ts"):
                if not (entry.path / asset).is_file():
                    warnings.append(f"{entry.name}: missing {asset}")
        return warnings
