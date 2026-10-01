"""M5 unit tests: CampaignPipeline stage wiring (fully mocked, offline)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from pulsecraft.pipeline.orchestrator import (
    CampaignError,
    CampaignPipeline,
    CampaignRequest,
    fallback_blueprints,
    parse_formats,
)


def _fakes(tmp_path: Path):
    media = MagicMock()
    media.fetch_scene.return_value = (
        {"url": "https://example.com/a.jpg", "provider": "pexels", "localPath": "cached"},
        [],
    )

    def _static_render(blueprint, brand="acme", out_dir="output"):
        out = Path(out_dir)
        square = out / "square-1080x1080.png"
        vertical = out / "vertical-1080x1350.png"
        meta = out / "static-meta.json"
        square.write_bytes(b"png")
        vertical.write_bytes(b"png")
        meta.write_text("{}", encoding="utf-8")
        return SimpleNamespace(
            png_square=square, png_vertical=vertical, meta_path=meta, warnings=[]
        )

    def _video_render(
        blueprint, brand="acme", preset="alex-hormozi", platform="all", out_dir="output"
    ):
        out = Path(out_dir)
        target = out / "reel-1080x1920.mp4"
        target.write_bytes(b"mp4")
        meta = out / "reel-meta.json"
        meta.write_text("{}", encoding="utf-8")
        return SimpleNamespace(files={"1080x1920": target}, meta_path=meta, warnings=["mock"])

    static = MagicMock()
    static.render_post.side_effect = _static_render
    video = MagicMock()
    video.render_reel.side_effect = _video_render
    return media, static, video


def test_parse_formats_and_empty_prompt() -> None:
    assert parse_formats("png,reel") == (True, True)
    assert parse_formats("png") == (True, False)
    assert parse_formats("reel") == (False, True)
    assert parse_formats("both") == (True, True)
    with pytest.raises(CampaignError):
        parse_formats("tiktok")
    with pytest.raises(CampaignError):
        CampaignPipeline().run(CampaignRequest(prompt="  "))


def test_fallback_blueprints_are_deterministic() -> None:
    post_a, reel_a = fallback_blueprints("hello habits", "acme", 7)
    post_b, reel_b = fallback_blueprints("hello habits", "acme", 7)
    assert post_a == post_b and reel_a == reel_b
    assert post_a["seed"] == 7 and reel_a["seed"] == 7


def test_run_bundles_output_dir_with_mocks(tmp_path: Path) -> None:
    media, static, video = _fakes(tmp_path)
    pipeline = CampaignPipeline(llm=None, media=media, static_renderer=static, video_renderer=video)
    result = pipeline.run(
        CampaignRequest(
            prompt="3 morning habits", brand="acme", run_id="run-test", out_dir=tmp_path / "output"
        )
    )
    assert result.run_dir.is_dir()
    assert (result.run_dir / "blueprint-post.json").is_file()
    assert (result.run_dir / "blueprint-reel.json").is_file()
    assert (result.run_dir / "assets.json").is_file()
    assert (result.run_dir / "ATTRIBUTION.md").is_file()
    assert (result.run_dir / "run-manifest.json").is_file()
    manifest = json.loads((result.run_dir / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == "run-test"
    assert manifest["timings_ms"]
    static.render_post.assert_called_once()
    video.render_reel.assert_called_once()


def test_run_png_only_skips_video(tmp_path: Path) -> None:
    media, static, video = _fakes(tmp_path)
    pipeline = CampaignPipeline(llm=None, media=media, static_renderer=static, video_renderer=video)
    result = pipeline.run(
        CampaignRequest(prompt="x", formats="png", run_id="r1", out_dir=tmp_path / "output")
    )
    static.render_post.assert_called_once()
    video.render_reel.assert_not_called()
    assert "run-manifest.json" in result.artifacts


def test_llm_failure_falls_back_to_offline_blueprints(tmp_path: Path) -> None:
    failing_llm = MagicMock()
    failing_llm.execute.side_effect = RuntimeError("429 down")
    media, static, video = _fakes(tmp_path)
    pipeline = CampaignPipeline(
        llm=failing_llm, media=media, static_renderer=static, video_renderer=video
    )
    result = pipeline.run(
        CampaignRequest(prompt="fallback me", run_id="r2", out_dir=tmp_path / "o")
    )
    assert result.post_blueprint["layout"] == "bold-hook-split"
    assert any("offline" in warning for warning in result.warnings)


def test_generate_campaign_cli_lists_all_groups() -> None:
    from pulsecraft.cli import main

    runner = CliRunner()
    top = runner.invoke(main, ["--help"])
    assert top.exit_code == 0
    for group in ("generate", "models", "render", "templates", "assets"):
        assert group in top.output
