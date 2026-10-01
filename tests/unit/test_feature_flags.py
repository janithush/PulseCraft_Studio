"""M3 unit tests: feature toggles + guardrails (toggles override prompts)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pulsecraft.common.feature_flags import FeatureFlags, FlagError

REPO_FLAGS = Path(__file__).resolve().parents[2] / "config" / "features.json"


def test_repo_features_all_enabled_by_default() -> None:
    flags = FeatureFlags.load(REPO_FLAGS)
    for dotted in (
        "tts.kokoro",
        "tts.edgeFallback",
        "stt.whisper",
        "audio.sfx",
        "audio.bgm",
        "audio.ducking",
        "media.pexels",
        "media.pixabay",
        "media.openverse",
        "media.localOverrides",
        "render.remotion",
        "render.dynamicL4",
    ):
        assert flags.enabled(dotted) is True, dotted


def test_missing_file_falls_back_to_defaults(tmp_path: Path) -> None:
    flags = FeatureFlags.load(tmp_path / "nope.json")
    assert flags.enabled("audio.bgm") is True


def test_cli_overrides_win_per_run_only(tmp_path: Path) -> None:
    path = tmp_path / "features.json"
    path.write_text(json.dumps({"version": "features/v1"}), encoding="utf-8")
    flags = FeatureFlags.from_cli({"audio.bgm": False, "media.pixabay": False}, path)
    assert flags.enabled("audio.bgm") is False
    assert flags.enabled("media.pixabay") is False
    assert flags.enabled("audio.sfx") is True
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == {"version": "features/v1"}


def test_guard_disabled_ignores_request() -> None:
    flags = FeatureFlags.from_cli({"audio.sfx": False})
    assert flags.guard("audio.sfx", True) is False
    assert flags.guard("audio.sfx", False) is False
    assert flags.guard("audio.bgm", True) is True


def test_enforce_strips_disabled_requests_with_warnings() -> None:
    flags = FeatureFlags.from_cli({"audio.bgm": False, "audio.sfx": False})
    cleaned, warnings = flags.enforce({"audioTags": ["crowd"], "keep": 1})
    assert "audioTags" not in cleaned
    assert cleaned["keep"] == 1
    assert any("audio.bgm" in warning for warning in warnings)


def test_unknown_feature_and_bad_file_raise(tmp_path: Path) -> None:
    flags = FeatureFlags.load(REPO_FLAGS)
    with pytest.raises(FlagError):
        flags.enabled("audio.ghost")
    with pytest.raises(FlagError):
        flags.set("audio.ghost", False)
    with pytest.raises(FlagError):
        flags.set("audio", False)
    with pytest.raises(FlagError):
        flags.enabled("audio")
    bad = tmp_path / "features.json"
    bad.write_text("{nope", encoding="utf-8")
    with pytest.raises(FlagError):
        FeatureFlags.load(bad)
    with pytest.raises(FlagError):
        FeatureFlags({"version": "features/v0"})
