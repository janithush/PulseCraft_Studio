"""M2 unit tests: StaticPostRenderer layers, dual-PNG export, CLI (browser mocked)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from PIL import Image

from pulsecraft.cli import main
from pulsecraft.render_static.renderer import RenderError, StaticPostRenderer

REPO_ROOT = Path(__file__).resolve().parents[2]


def _renderer() -> StaticPostRenderer:
    return StaticPostRenderer(
        templates_root=REPO_ROOT / "templates", brands_root=REPO_ROOT / "brands"
    )


def _blueprint(**overrides) -> dict:
    base = {
        "type": "static-post",
        "brand": "acme",
        "layout": "bold-hook-split",
        "canvas": ["1080x1080", "1080x1350"],
        "copy": {"hook": "H", "sub": "S", "cta": "C"},
        "bullets": ["a", "b"],
    }
    base.update(overrides)
    return base


def _fake_shot(self, html, width, height, out_path) -> int:
    Image.new("RGB", (width, height), "white").save(out_path)
    return 5


def test_resolve_layer_l3_known_l4_unknown() -> None:
    renderer = _renderer()
    assert renderer.resolve_layer(_blueprint()) == "L3"
    assert renderer.resolve_layer(_blueprint(layout="no-such-layout")) == "L4"


def test_load_brand_falls_back_to_base_with_warning() -> None:
    tokens, warnings = _renderer().load_brand("acme")
    assert tokens["colors"]["primary"] == "#FF4D00"
    assert any("falling back" in warning for warning in warnings)


def test_load_brand_without_base_raises(tmp_path: Path) -> None:
    renderer = StaticPostRenderer(
        templates_root=REPO_ROOT / "templates", brands_root=tmp_path / "brands"
    )
    with pytest.raises(RenderError):
        renderer.load_brand("ghost")


def test_render_post_l3_writes_both_pngs_and_meta(tmp_path: Path) -> None:
    renderer = _renderer()
    with patch.object(StaticPostRenderer, "_screenshot", _fake_shot):
        result = renderer.render_post(_blueprint(), brand="acme", out_dir=tmp_path)
    assert result.layer == "L3"
    assert result.template_id == "bold-hook-split"
    for path, size in ((result.png_square, (1080, 1080)), (result.png_vertical, (1080, 1350))):
        assert path.is_file()
        with Image.open(path) as image:
            assert (image.width, image.height) == size
    meta = json.loads(result.meta_path.read_text(encoding="utf-8"))
    assert meta["layer"] == "L3"
    assert meta["dimensions"] == {"1080x1080": [1080, 1080], "1080x1350": [1080, 1350]}
    assert all("sha256" in entry for entry in meta["files"].values())


def test_render_post_l4_uses_llm_html_and_logs_model(tmp_path: Path) -> None:
    fake_orch = MagicMock()
    fake_orch.execute.return_value = MagicMock(
        text="```html\n<html><head></head><body>L4</body></html>\n```",
        model_used="vendor/model:free",
    )
    renderer = StaticPostRenderer(
        templates_root=REPO_ROOT / "templates",
        brands_root=REPO_ROOT / "brands",
        orchestrator=fake_orch,
    )
    with patch.object(StaticPostRenderer, "_screenshot", _fake_shot):
        result = renderer.render_post(
            _blueprint(layout="non-standard"), brand="acme", out_dir=tmp_path
        )
    assert result.layer == "L4"
    assert result.template_id == "dynamic:non-standard"
    meta = json.loads(result.meta_path.read_text(encoding="utf-8"))
    assert meta["modelUsed"] == "vendor/model:free"
    fake_orch.execute.assert_called()


def test_render_post_l4_rejects_remote_urls(tmp_path: Path) -> None:
    fake_orch = MagicMock()
    fake_orch.execute.return_value = MagicMock(
        text='<img src="https://evil.example/x.png">', model_used="m"
    )
    renderer = StaticPostRenderer(
        templates_root=REPO_ROOT / "templates",
        brands_root=REPO_ROOT / "brands",
        orchestrator=fake_orch,
    )
    with (
        patch.object(StaticPostRenderer, "_screenshot", _fake_shot),
        pytest.raises(RenderError),
    ):
        renderer.render_post(_blueprint(layout="non-standard"), brand="acme", out_dir=tmp_path)


def test_render_post_rejects_non_static_blueprint(tmp_path: Path) -> None:
    with (
        patch.object(StaticPostRenderer, "_screenshot", _fake_shot),
        pytest.raises(RenderError),
    ):
        _renderer().render_post(_blueprint(type="reel"), brand="acme", out_dir=tmp_path)


def test_assert_dimensions_mismatch_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.png"
    Image.new("RGB", (10, 10), "white").save(bad)
    with pytest.raises(RenderError):
        _renderer()._assert_dimensions(bad, 1080, 1080)


def test_tokens_css_exposes_brand_vars() -> None:
    css = _renderer().tokens_css({"colors": {"bg": "#111"}, "fonts": {"display": "Inter"}})
    assert "--brand-bg: #111" in css
    assert "--brand-display: Inter" in css


def test_cli_render_post_and_templates_inspect(tmp_path: Path) -> None:
    blueprint_path = tmp_path / "blueprint.json"
    blueprint_path.write_text(json.dumps(_blueprint()), encoding="utf-8")
    runner = CliRunner()
    with patch.object(StaticPostRenderer, "_screenshot", _fake_shot):
        result = runner.invoke(
            main,
            [
                "render",
                "post",
                "--blueprint",
                str(blueprint_path),
                "--brand",
                "acme",
                "--out",
                str(tmp_path / "out"),
            ],
        )
    assert result.exit_code == 0, result.output
    assert "layer: L3" in result.output
    assert (tmp_path / "out" / "meta.json").is_file()

    listed = runner.invoke(main, ["templates", "list", "--kind", "posts"])
    assert listed.exit_code == 0, listed.output
    assert "bold-hook-split" in listed.output
    assert "minimal-type" in listed.output

    inspected = runner.invoke(main, ["templates", "inspect", "bold-hook-split"])
    assert inspected.exit_code == 0, inspected.output
    assert "required: hook" in inspected.output
    assert "[Hook Here]" in inspected.output

    missing = runner.invoke(main, ["templates", "inspect", "ghost"])
    assert missing.exit_code != 0
