"""M3 unit tests: visual tags, local overrides, provider cascade, audio fetch."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pulsecraft.assets.audio_fetcher import AudioFetcher
from pulsecraft.assets.media_fetcher import (
    MediaError,
    MediaFetcher,
    extract_visual_tags,
    fetch_openverse,
    resolve_local_override,
)


def test_extract_visual_tags() -> None:
    script = "Intro [Visual: my-product.png] then [Visual:hero shot]"
    assert extract_visual_tags(script) == ["my-product.png", "hero shot"]
    assert extract_visual_tags("no tags") == []


def test_resolve_local_override_guards_traversal(tmp_path: Path) -> None:
    visuals = tmp_path / "input" / "visuals"
    visuals.mkdir(parents=True)
    target = visuals / "my-product.png"
    target.write_bytes(b"png")
    assert resolve_local_override("my-product.png", visuals) == target.resolve()
    assert resolve_local_override("missing.png", visuals) is None
    assert resolve_local_override("../escape.png", visuals) is None


def test_fetch_scene_prefers_local_and_cascades(tmp_path: Path) -> None:
    visuals = tmp_path / "visuals"
    visuals.mkdir()
    (visuals / "hero.png").write_bytes(b"png")
    fetcher = MediaFetcher(cache_dir=tmp_path / "cache", visuals_dir=visuals)
    asset, warnings = fetcher.fetch_scene("hero.png")
    assert asset["provider"] == "local"
    assert warnings == []

    with (
        patch("pulsecraft.assets.media_fetcher.fetch_pexels", return_value=[]),
        patch(
            "pulsecraft.assets.media_fetcher.fetch_pixabay",
            return_value=[{"url": "u", "photographer": "p", "license": "l", "provider": "pixabay"}],
        ),
    ):
        asset, warnings = fetcher.fetch_scene("sunset reel")
    assert asset["provider"] == "pixabay"
    assert any("pexels" in warning for warning in warnings)


def test_fetch_scene_strict_raises_and_manifest_writes(tmp_path: Path) -> None:
    fetcher = MediaFetcher(cache_dir=tmp_path / "c", visuals_dir=tmp_path / "v")
    with (
        patch("pulsecraft.assets.media_fetcher.fetch_pexels", return_value=[]),
        patch("pulsecraft.assets.media_fetcher.fetch_pixabay", return_value=[]),
        patch("pulsecraft.assets.media_fetcher.fetch_openverse", return_value=[]),
    ):
        with pytest.raises(MediaError):
            fetcher.fetch_scene("nothing", strict=True)
        asset, warnings = fetcher.fetch_scene("nothing")
    assert asset["provider"] == "fallback"
    manifest = fetcher.write_manifest([asset], tmp_path / "manifest.json")
    assert json.loads(manifest.read_text(encoding="utf-8"))[0]["provider"] == "fallback"


def test_openverse_failure_returns_empty() -> None:
    with patch("pulsecraft.assets.media_fetcher._get", side_effect=RuntimeError("down")):
        assert fetch_openverse("cats") == []


def test_audio_fetch_respects_toggle_and_missing_keys() -> None:
    fetcher = AudioFetcher()
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("FREESOUND_API_KEY", None)
        os.environ.pop("PIXABAY_API_KEY", None)
        hits, warnings = fetcher.fetch(["crowd"], kind="sfx")
        assert hits == [] and warnings
    from pulsecraft.common.feature_flags import FeatureFlags

    disabled = FeatureFlags.from_cli({"audio.bgm": False})
    hits, warnings = AudioFetcher(flags=disabled).fetch(["calm"], kind="bgm")
    assert hits == [] and any("audio.bgm" in warning for warning in warnings)


def test_audio_fetch_caches_first_hit(tmp_path: Path) -> None:
    fetcher = AudioFetcher(cache_dir=tmp_path)
    hit = {"url": "u", "name": "n", "license": "l", "provider": "pixabay-audio"}
    with patch("pulsecraft.assets.audio_fetcher.fetch_pixabay_bgm", return_value=[hit]):
        hits, _ = fetcher.fetch(["calm"], kind="bgm")
    assert hits[0]["localPath"].startswith(str(tmp_path))
    assert Path(hits[0]["localPath"]).parent.name == "bgm"
