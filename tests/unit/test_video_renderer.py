"""M3 unit tests: VideoReelRenderer platforms/presets/guardrails + CLI (mocked)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from pulsecraft.cli import main
from pulsecraft.common.feature_flags import FeatureFlags
from pulsecraft.render_video.renderer import (
    PLATFORM_CANVASES,
    VideoReelRenderer,
    VideoRenderError,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _blueprint(**overrides) -> dict:
    base = {
        "type": "reel",
        "brand": "acme",
        "layout": "kinetic-bold",
        "durationTargetSec": 30,
        "script": [
            {"id": "s1", "voText": "Stop skipping breakfast."},
            {"id": "s2", "voText": "Three protein mornings change everything."},
        ],
        "scenes": [{"id": "scene-1", "assetQuery": "oatmeal bowl bright"}],
        "audioTags": ["calm"],
        "style": {"presetTweaks": {"highlight": "green", "nope": 1}},
    }
    base.update(overrides)
    return base


def _renderer(**overrides) -> VideoReelRenderer:
    defaults = {
        "remotion_root": REPO_ROOT / "remotion",
        "templates_root": REPO_ROOT / "templates",
        "brands_root": REPO_ROOT / "brands",
        "flags": FeatureFlags.load(),
    }
    defaults.update(overrides)
    return VideoReelRenderer(**defaults)


def _ok_runner(targets: dict[str, Path]):
    def run(cmd: list[str], cwd: Path):
        target = Path(cmd[4])
        target.write_bytes(b"mp4")
        targets[target.name] = target
        return SimpleNamespace(returncode=0, stderr="")

    return run


def test_platform_canvases_and_unknown() -> None:
    renderer = _renderer()
    assert renderer.platform_canvases("fb") == ["1080x1080", "1080x1920"]
    assert renderer.platform_canvases("ig") == ["1080x1350", "1080x1920"]
    assert renderer.platform_canvases("all") == PLATFORM_CANVASES["all"]
    with pytest.raises(VideoRenderError):
        renderer.platform_canvases("tiktok")


def test_unknown_preset_and_missing_pack() -> None:
    with pytest.raises(VideoRenderError):
        _renderer().check_preset("ghost")
    renderer = _renderer(templates_root=REPO_ROOT / "templates-missing")
    with pytest.raises(VideoRenderError):
        renderer.check_preset("alex-hormozi")


def test_render_reel_all_platforms_with_mocks(tmp_path: Path) -> None:
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"voice")
    tts = MagicMock()
    tts.synthesize.return_value = (voice, True)
    stt = MagicMock()
    stt.transcribe.return_value = {
        "words": [{"word": "Stop", "start": 0.1, "end": 0.3}],
        "model": "base-int8",
        "estimated": False,
    }
    media = MagicMock()
    media.fetch_scene.return_value = ({"url": "u", "provider": "pexels", "localPath": ""}, [])
    audio_fetcher = MagicMock()
    audio_fetcher.fetch.return_value = ([], ["no bgm file"])
    made: dict[str, Path] = {}
    renderer = _renderer(
        tts=tts, stt=stt, media=media, audio_fetcher=audio_fetcher, runner=_ok_runner(made)
    )
    result = renderer.render_reel(
        _blueprint(), brand="acme", preset="alex-hormozi", platform="all", out_dir=tmp_path
    )
    assert set(result.files) == {"1080x1080", "1080x1350", "1080x1920"}
    assert all(path.is_file() for path in result.files.values())
    meta = json.loads(result.meta_path.read_text(encoding="utf-8"))
    assert meta["preset"] == "alex-hormozi"
    assert meta["presetTweaks"] == {"highlight": "green"}
    assert any("nope" in warning for warning in result.warnings)
    props = json.loads((tmp_path / "props-1080x1920.json").read_text(encoding="utf-8"))
    assert props["width"] == 1080 and props["height"] == 1920
    assert props["words"][0]["word"] == "Stop"


def test_render_reel_no_bgm_toggle_skips_bed(tmp_path: Path) -> None:
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"voice")
    tts = MagicMock()
    tts.synthesize.return_value = (voice, True)
    stt = MagicMock()
    stt.transcribe.return_value = {"words": [], "model": "uniform", "estimated": True}
    flags = FeatureFlags.from_cli({"audio.bgm": False, "audio.sfx": False})
    renderer = _renderer(tts=tts, stt=stt, media=MagicMock(), flags=flags, runner=_ok_runner({}))
    with patch.object(VideoReelRenderer, "_media_fetch", return_value=({}, [])):
        result = renderer.render_reel(
            _blueprint(), brand="acme", preset="faceless-docu", platform="fb", out_dir=tmp_path
        )
    assert set(result.files) == {"1080x1080", "1080x1920"}
    assert any("audio.bgm" in warning for warning in result.warnings)
    assert not (tmp_path / "mix-voice-bgm.wav").exists()


def test_render_reel_rejects_bad_blueprint_and_failed_render(tmp_path: Path) -> None:
    renderer = _renderer(runner=_ok_runner({}))
    with pytest.raises(VideoRenderError):
        renderer.render_reel(_blueprint(type="static-post"), out_dir=tmp_path)

    def fail_runner(cmd: list[str], cwd: Path) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stderr="boom")

    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"voice")
    tts = MagicMock()
    tts.synthesize.return_value = (voice, True)
    stt = MagicMock()
    stt.transcribe.return_value = {"words": [], "model": "uniform", "estimated": True}
    media = MagicMock()
    media.fetch_scene.return_value = ({}, [])
    renderer = _renderer(tts=tts, stt=stt, media=media, runner=fail_runner)
    with pytest.raises(VideoRenderError):
        renderer.render_reel(_blueprint(), preset="b-roll-centric", out_dir=tmp_path)


def test_cli_render_reel_reports_files(tmp_path: Path) -> None:
    blueprint_path = tmp_path / "reel.json"
    blueprint_path.write_text(json.dumps(_blueprint()), encoding="utf-8")
    runner = CliRunner()
    with (
        patch(
            "pulsecraft.render_video.renderer.VideoReelRenderer._voice_and_words",
            return_value=(None, [], None, True, []),
        ),
        patch(
            "pulsecraft.render_video.renderer.VideoReelRenderer._scenes", return_value=([], [], [])
        ),
        patch(
            "pulsecraft.render_video.renderer.VideoReelRenderer._remotion_render",
            side_effect=lambda preset, props, target, w, h, warns: target.write_bytes(b"m"),
        ),
    ):
        result = runner.invoke(
            main,
            [
                "render",
                "reel",
                "--blueprint",
                str(blueprint_path),
                "--brand",
                "acme",
                "--preset",
                "b-roll-centric",
                "--platform",
                "ig",
                "--out",
                str(tmp_path / "out"),
                "--no-bgm",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "preset: b-roll-centric platform: ig" in result.output
    assert "1080x1350" in result.output and "1080x1920" in result.output
    assert (tmp_path / "out" / "reel-meta.json").is_file()
