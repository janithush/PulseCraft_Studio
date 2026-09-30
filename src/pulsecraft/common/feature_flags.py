"""Feature Toggles & API Guardrails Engine (M3).

Rule (normative): system toggles strictly override LLM prompts. A disabled
feature's blueprint/prompt requests are ignored with a logged warning.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

FEATURES_VERSION = "features/v1"

DEFAULTS: dict[str, Any] = {
    "version": FEATURES_VERSION,
    "tts": {"kokoro": {"enabled": True}, "edgeFallback": {"enabled": True}},
    "stt": {"whisper": {"enabled": True}},
    "audio": {
        "sfx": {"enabled": True},
        "bgm": {"enabled": True},
        "ducking": {"enabled": True},
    },
    "media": {
        "pexels": {"enabled": True},
        "pixabay": {"enabled": True},
        "openverse": {"enabled": True},
        "localOverrides": {"enabled": True},
    },
    "render": {"remotion": {"enabled": True}, "dynamicL4": {"enabled": True}},
}

BLUEPRINT_GUARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("audio.sfx", ("audioTags",)),
    ("audio.bgm", ("audioTags",)),
    ("media.localOverrides", ("visualTags",)),
    ("render.dynamicL4", ("variantHint",)),
)


class FlagError(ValueError):
    """Unknown feature path or malformed `features.json`."""


class FeatureFlags:
    """Hierarchical toggles: file values, CLI overrides win per-run only."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = _validate(data)

    @classmethod
    def load(cls, path: str | Path = "config/features.json") -> FeatureFlags:
        config_path = Path(path)
        if not config_path.is_file():
            return cls(copy.deepcopy(DEFAULTS))
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FlagError(f"features file is not valid JSON: {config_path}: {exc}") from exc
        return cls(raw)

    @classmethod
    def from_cli(
        cls, overrides: dict[str, bool] | None = None, path: str | Path = "config/features.json"
    ) -> FeatureFlags:
        flags = cls.load(path)
        for dotted, value in (overrides or {}).items():
            flags.set(dotted, value)
        return flags

    def enabled(self, dotted: str) -> bool:
        node = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                raise FlagError(f"unknown feature '{dotted}'")
            node = node[part]
        if isinstance(node, dict) and "enabled" in node:
            return bool(node["enabled"])
        raise FlagError(f"feature '{dotted}' is a group, not a toggle")

    def set(self, dotted: str, value: bool) -> None:
        node = self._data
        parts = dotted.split(".")
        for part in parts[:-1]:
            if not isinstance(node, dict) or part not in node:
                raise FlagError(f"unknown feature '{dotted}'")
            node = node[part]
        leaf = parts[-1]
        if not isinstance(node, dict) or leaf not in node:
            raise FlagError(f"unknown feature '{dotted}'")
        target = node[leaf]
        if isinstance(target, dict) and "enabled" in target:
            target["enabled"] = bool(value)
            return
        raise FlagError(f"feature '{dotted}' is a group, not a toggle")

    def guard(self, dotted: str, requested: bool) -> bool:
        """Toggle AND request: disabled features ignore blueprint asks."""
        return self.enabled(dotted) and bool(requested)

    def enforce(self, blueprint: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """Strip disabled-feature requests from a blueprint copy; list warnings."""
        cleaned = copy.deepcopy(blueprint)
        warnings: list[str] = []
        disabled_by_key: dict[str, list[str]] = {}
        for dotted, keys in BLUEPRINT_GUARDS:
            if self.enabled(dotted):
                continue
            for key in keys:
                disabled_by_key.setdefault(key, []).append(dotted)
        for key, dotted_names in disabled_by_key.items():
            if key in cleaned:
                del cleaned[key]
                names = ", ".join(f"'{name}'" for name in dotted_names)
                warnings.append(f"toggles {names} disabled: ignoring blueprint '{key}'")
        return cleaned, warnings

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)


def _validate(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise FlagError("features root must be an object")
    if raw.get("version") != FEATURES_VERSION:
        raise FlagError(f"unsupported version '{raw.get('version')}'. Want '{FEATURES_VERSION}'")
    data = copy.deepcopy(DEFAULTS)
    _merge(data, raw)
    return data


def _merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if key == "version":
            continue
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        elif key in base:
            base[key] = value
