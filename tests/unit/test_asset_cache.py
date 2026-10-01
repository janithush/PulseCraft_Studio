"""M4 unit tests: hash-indexed disk asset cache (hit/miss, dedupe, eviction)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from pulsecraft.assets.cache import AssetCache, cache_key


def test_cache_key_is_stable_and_hex(tmp_path: Path) -> None:
    first = cache_key("pexels", "sunset", "https://example.com/a.jpg")
    assert first == cache_key("pexels", "sunset", "https://example.com/a.jpg")
    assert len(first) == 16 and all(c in "0123456789abcdef" for c in first)
    assert first != cache_key("pixabay", "sunset", "https://example.com/a.jpg")
    _ = tmp_path  # keep signature uniform with sibling tests


def test_put_then_get_hits_without_network(tmp_path: Path) -> None:
    cache = AssetCache(tmp_path / "assets")
    assert cache.get("pexels", "cats", "https://example.com/c.jpg") is None
    stored = cache.put("pexels", "cats", "https://example.com/c.jpg", b"bytes-123")
    assert stored.is_file()
    assert cache.get("pexels", "cats", "https://example.com/c.jpg") == stored
    assert len(cache.list_cached()) == 1


def test_fetch_or_download_suppresses_duplicate_requests(tmp_path: Path) -> None:
    cache = AssetCache(tmp_path / "assets")
    calls: list[int] = []

    def downloader() -> bytes:
        calls.append(1)
        return b"remote-bytes"

    first = cache.fetch_or_download("openverse", "dogs", "https://example.com/d.png", downloader)
    second = cache.fetch_or_download("openverse", "dogs", "https://example.com/d.png", downloader)
    assert first == second
    assert calls == [1]


def test_clear_empties_cache_and_cli_lists_assets(tmp_path: Path) -> None:
    from pulsecraft.cli import main

    cache_dir = tmp_path / "assets"
    cache = AssetCache(cache_dir)
    cache.put("freesound", "crowd", "https://example.com/c.mp3", b"audio")
    assert len(cache.list_cached()) == 1

    runner = CliRunner()
    listed = runner.invoke(main, ["assets", "list", "--cache-dir", str(cache_dir)])
    assert listed.exit_code == 0
    assert "cached remote assets" in listed.output

    cleared = runner.invoke(main, ["assets", "clear-cache", "--cache-dir", str(cache_dir)])
    assert cleared.exit_code == 0
    assert "cleared 1" in cleared.output
    assert cache.list_cached() == []


def test_evict_lru_drops_oldest_first(tmp_path: Path) -> None:
    cache = AssetCache(tmp_path / "assets")
    cache.put("pexels", "a", "https://example.com/a.bin", b"1" * 10)
    cache.put("pexels", "b", "https://example.com/b.bin", b"2" * 10)
    evicted = cache.evict_lru(max_bytes=15)
    assert evicted == 1
    assert len(cache.list_cached()) == 1
