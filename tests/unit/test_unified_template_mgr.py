"""M4 unit tests: unified post+reel template registry + strict validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pulsecraft.templates_mgr.registry import RegistryError, UnifiedTemplateRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = UnifiedTemplateRegistry(REPO_ROOT / "templates")


def test_list_all_templates_covers_posts_and_reels() -> None:
    entries = REGISTRY.list_all_templates()
    kinds = {(entry.kind, entry.name) for entry in entries}
    assert ("post", "bold-hook-split") in kinds
    assert ("post", "minimal-type") in kinds
    assert ("reel", "alex-hormozi") in kinds
    assert ("reel", "kinetic-bold") in kinds
    assert len(entries) >= 6


def test_get_template_schema_returns_manifest_and_placeholders() -> None:
    post = REGISTRY.get_template_schema("bold-hook-split")
    assert post["kind"] == "post"
    assert post["manifest"]["layoutId"] == "bold-hook-split"
    assert "hook" in post["placeholders"]["required"]

    reel = REGISTRY.get_template_schema("alex-hormozi")
    assert reel["kind"] == "reel"
    assert reel["manifest"]["themeId"] == "alex-hormozi"
    assert "script" in reel["placeholders"]["required"]


def test_get_template_schema_unknown_raises() -> None:
    with pytest.raises(RegistryError) as exc_info:
        REGISTRY.get_template_schema("ghost-pack")
    assert "bold-hook-split" in str(exc_info.value)


def test_validate_all_templates_clean_on_repo_packs() -> None:
    results = REGISTRY.validate_all_templates()
    assert results
    failures = {key: warnings for key, warnings in results.items() if warnings}
    assert failures == {}


def test_validate_flags_broken_manifest(tmp_path: Path) -> None:
    posts = tmp_path / "templates" / "posts"
    reels = tmp_path / "templates" / "reels"
    broken = posts / "broken-pack"
    broken.mkdir(parents=True)
    reels.mkdir(parents=True)
    (broken / "meta.json").write_text(json.dumps({"displayName": "Broken"}), encoding="utf-8")
    (broken / "index.html").write_text("{{ hook }}", encoding="utf-8")
    (broken / "style.css").write_text("body {}", encoding="utf-8")

    results = UnifiedTemplateRegistry(tmp_path / "templates").validate_all_templates()
    assert "posts/broken-pack" in results
    joined = " ".join(results["posts/broken-pack"])
    assert "layoutId" in joined


def test_templates_validate_cli_passes_on_repo_packs() -> None:
    from pulsecraft.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["templates", "validate"])
    assert result.exit_code == 0
    assert "all clean" in result.output
