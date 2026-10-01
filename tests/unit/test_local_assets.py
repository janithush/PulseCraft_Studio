"""M4 unit tests: local asset indexer (visuals + audio, metadata, tag match)."""

from __future__ import annotations

import wave
from pathlib import Path

from click.testing import CliRunner

from pulsecraft.assets.local_mgr import find_for_tag, index_local_assets, normalize_tag


def _write_png(path: Path, width: int = 8, height: int = 6) -> None:
    from PIL import Image

    img = Image.new("RGB", (width, height), color="red")
    img.save(path)


def _write_wav(path: Path, seconds: float = 0.5, rate: int = 8000) -> None:
    frames = int(seconds * rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * frames)


def test_index_extracts_image_dims_and_wav_meta(tmp_path: Path) -> None:
    visuals = tmp_path / "visuals"
    audio = tmp_path / "audio"
    visuals.mkdir()
    audio.mkdir()
    _write_png(visuals / "hero.png", 8, 6)
    _write_wav(audio / "bed.wav", 0.5, 8000)
    (visuals / "notes.txt").write_text("skip me", encoding="utf-8")

    assets = index_local_assets(visuals, audio)
    by_name = {item.name: item for item in assets}
    assert set(by_name) == {"hero.png", "bed.wav"}
    assert (by_name["hero.png"].width, by_name["hero.png"].height) == (8, 6)
    assert by_name["hero.png"].kind == "image"
    assert by_name["bed.wav"].kind == "audio"
    assert abs(by_name["bed.wav"].duration_sec - 0.5) < 0.05
    assert by_name["bed.wav"].sample_rate_hz == 8000


def test_tag_matching_is_case_insensitive_and_traversal_guarded(tmp_path: Path) -> None:
    visuals = tmp_path / "visuals"
    audio = tmp_path / "audio"
    visuals.mkdir()
    audio.mkdir()
    _write_png(visuals / "My-Product.PNG")
    assert normalize_tag("[Visual: my-product.png]") == "my-product.png"
    found = find_for_tag("[Visual: MY-PRODUCT.png]", visuals, audio)
    assert found is not None and found.name == "My-Product.PNG"
    assert find_for_tag("missing.png", visuals, audio) is None
    assert find_for_tag("../escape.png", visuals, audio) is None
    assert find_for_tag("", visuals, audio) is None


def test_assets_list_cli_shows_local_and_cached(tmp_path: Path) -> None:
    from pulsecraft.cli import main

    visuals = tmp_path / "visuals"
    audio = tmp_path / "audio"
    visuals.mkdir()
    audio.mkdir()
    _write_png(visuals / "hero.png")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "assets",
            "list",
            "--visuals",
            str(visuals),
            "--audio",
            str(audio),
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 0
    assert "hero.png" in result.output
    assert "local assets" in result.output
