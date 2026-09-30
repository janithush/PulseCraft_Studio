"""M2 unit tests: TemplateManager scan/list/validate/hydrate/inspect (L1/L2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pulsecraft.templates_mgr.manager import (
    TemplateError,
    TemplateManager,
    lint_offline_safety,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MANAGER = TemplateManager(REPO_ROOT / "templates")


def test_list_finds_both_post_layouts() -> None:
    assert MANAGER.names("posts") == ["bold-hook-split", "minimal-type"]
    assert MANAGER.names("nope") == []


def test_get_unknown_lists_available() -> None:
    with pytest.raises(TemplateError) as exc_info:
        MANAGER.get("ghost", kind="posts")
    assert "bold-hook-split" in str(exc_info.value)


def test_validate_clean_template_has_no_warnings() -> None:
    assert MANAGER.validate("bold-hook-split", kind="posts") == []
    assert MANAGER.validate("minimal-type", kind="posts") == []


def test_validate_flags_remote_url_and_missing_meta(tmp_path: Path) -> None:
    pack = tmp_path / "templates" / "posts" / "remote-pack"
    pack.mkdir(parents=True)
    (pack / "index.html").write_text(
        '<link rel="stylesheet" href="https://cdn.example/x.css">{{ hook }}',
        encoding="utf-8",
    )
    (pack / "style.css").write_text("body { color: red; }", encoding="utf-8")
    manager = TemplateManager(tmp_path / "templates")
    warnings = manager.validate("remote-pack", kind="posts")
    assert any("missing meta.json" in warning for warning in warnings)
    assert any("remote URL" in warning for warning in warnings)


def test_hydrate_l1_hides_empty_optionals() -> None:
    full = MANAGER.hydrate("bold-hook-split", {"hook": "H", "sub": "S", "cta": "C"})
    assert "S" in full and "C" in full
    bare = MANAGER.hydrate("bold-hook-split", {"hook": "H", "sub": "", "cta": ""})
    assert 'class="sub"' not in bare
    assert 'class="cta"' not in bare


def test_hydrate_l2_iterates_bullets_and_hashtags() -> None:
    html = MANAGER.hydrate(
        "bold-hook-split",
        {"hook": "H", "bullets": ["a", "b", "c"], "hashtags": ["#x", "#y"]},
    )
    assert html.count("<li>") == 3
    assert html.count("<span>") == 2


def test_inspect_returns_badges_and_schema() -> None:
    preview = MANAGER.inspect_template("bold-hook-split", kind="posts")
    assert "[Hook Here]" in preview["html"]
    assert "[CTA Here]" in preview["html"]
    assert preview["schema"]["required"] == ["hook"]
    assert {"sub", "cta", "bullets"} <= set(preview["schema"]["optional"])
    assert preview["warnings"] == []
    assert preview["canvas"] == "square"


def test_inspect_unknown_raises() -> None:
    with pytest.raises(TemplateError):
        MANAGER.inspect_template("ghost", kind="posts")


def test_lint_offline_safety_rejects_remote() -> None:
    with pytest.raises(TemplateError):
        lint_offline_safety('<img src="http://example.com/x.png">', source="test")
    lint_offline_safety("<div>local only</div>", source="test")
