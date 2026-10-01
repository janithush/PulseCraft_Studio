"""M5 integration: `generate campaign` CLI end-to-end with mocked renderers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from click.testing import CliRunner


def _mock_pipeline(monkey_tmp: Path):
    media = MagicMock()
    media.fetch_scene.return_value = (
        {"url": "", "provider": "fallback", "localPath": ""},
        ["fallback used"],
    )

    def _static(blueprint, brand="acme", out_dir="output"):
        out = Path(out_dir)
        (out / "square-1080x1080.png").write_bytes(b"png")
        (out / "vertical-1080x1350.png").write_bytes(b"png")
        (out / "static-meta.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(
            png_square=out / "square-1080x1080.png",
            png_vertical=out / "vertical-1080x1350.png",
            meta_path=out / "static-meta.json",
            warnings=[],
        )

    def _video(blueprint, brand="acme", preset="alex-hormozi", platform="all", out_dir="output"):
        out = Path(out_dir)
        (out / "reel-1080x1920.mp4").write_bytes(b"mp4")
        (out / "reel-meta.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(
            files={"1080x1920": out / "reel-1080x1920.mp4"},
            meta_path=out / "reel-meta.json",
            warnings=[],
        )

    static = MagicMock()
    static.render_post.side_effect = _static
    video = MagicMock()
    video.render_reel.side_effect = _video
    return media, static, video


def test_generate_campaign_e2e_offline(tmp_path: Path) -> None:
    from pulsecraft.cli import main
    from pulsecraft.pipeline import orchestrator as orch

    media, static, video = _mock_pipeline(tmp_path)
    with (
        patch.object(orch.CampaignPipeline, "_default_llm", return_value=None),
        patch.object(orch.CampaignPipeline, "_default_media", return_value=media),
        patch.object(orch.CampaignPipeline, "_static_renderer", return_value=static),
        patch.object(orch.CampaignPipeline, "_video_renderer", return_value=video),
    ):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "generate",
                "campaign",
                "--prompt",
                "3 morning habits",
                "--brand",
                "acme",
                "--formats",
                "png,reel",
                "--seed",
                "42",
                "--out",
                str(tmp_path / "output"),
            ],
        )
    assert result.exit_code == 0, result.output
    assert "run:" in result.output
    run_dirs = list((tmp_path / "output").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    for name in ("blueprint-post.json", "blueprint-reel.json", "assets.json", "run-manifest.json"):
        assert (run_dir / name).is_file(), name
