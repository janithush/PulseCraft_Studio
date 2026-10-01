"""Phase-2 pre-flight auditor tests (hard-block contract)."""

from __future__ import annotations

import pytest

from pulsecraft.common.preflight import PreflightError, run_preflight


def test_preflight_passes_with_all_checks_disabled(tmp_path) -> None:
    result = run_preflight(
        root=tmp_path,
        strict=True,
        check_packages=False,
        check_binaries=False,
        check_env=False,
        check_dirs=False,
    )
    assert result.ok is True


def test_preflight_strict_raises_with_diagnostic(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    with pytest.raises(PreflightError, match="Pre-flight Failed"):
        run_preflight(root=tmp_path, strict=True)


def test_preflight_non_strict_reports_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    result = run_preflight(root=tmp_path, strict=False)
    assert result.diagnostic().startswith("❌ Pre-flight Failed")
    # dirs are auto-created so only packages/binaries/env should be missing here
    assert result.unwritable_dirs == []


def test_preflight_unwritable_dir_detected(tmp_path) -> None:
    # Point root at a file (not a dir) so mkdir fails -> unwritable
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    result = run_preflight(
        root=blocker / "nested",
        strict=False,
        check_packages=False,
        check_binaries=False,
        check_env=False,
        check_dirs=True,
    )
    assert result.ok is False
    assert result.unwritable_dirs
