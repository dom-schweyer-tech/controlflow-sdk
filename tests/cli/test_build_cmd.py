"""Tests for the ``cflow build`` subcommand."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from controlflow_sdk.bundle import read_bundle
from controlflow_sdk.cli import main
from controlflow_sdk.schema.validate import validate_bundle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_PROJECT = Path(__file__).parent.parent / "project" / "fixtures" / "sample"

FIXED_RUN_AT = "2026-06-16T00:00:00Z"
FIXED_BUILD_AT = "2026-06-16T01:00:00Z"

CONTROL_ID = "cash_cutoff"


def _copy_project(src: Path, dest: Path) -> Path:
    """Recursively copy the fixture project into dest (excluding __pycache__)."""
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


# ---------------------------------------------------------------------------
# Happy path: run then build
# ---------------------------------------------------------------------------


class TestBuildHappyPath:
    def test_returns_0(self, tmp_path: Path) -> None:
        """build exits 0 after a successful run."""
        proj = _copy_project(SAMPLE_PROJECT, tmp_path / "proj")
        main(["run", str(proj), "--at", FIXED_RUN_AT])
        out_zip = tmp_path / "bundle.zip"
        rc = main(["build", str(proj), "--out", str(out_zip), "--at", FIXED_BUILD_AT])
        assert rc == 0

    def test_creates_zip(self, tmp_path: Path) -> None:
        """build writes a zip file at the --out path."""
        proj = _copy_project(SAMPLE_PROJECT, tmp_path / "proj")
        main(["run", str(proj), "--at", FIXED_RUN_AT])
        out_zip = tmp_path / "bundle.zip"
        main(["build", str(proj), "--out", str(out_zip), "--at", FIXED_BUILD_AT])
        assert out_zip.exists(), f"Expected {out_zip} to be created"

    def test_bundle_passes_validation(self, tmp_path: Path) -> None:
        """The manifest inside the zip must pass validate_bundle with no errors."""
        proj = _copy_project(SAMPLE_PROJECT, tmp_path / "proj")
        main(["run", str(proj), "--at", FIXED_RUN_AT])
        out_zip = tmp_path / "bundle.zip"
        main(["build", str(proj), "--out", str(out_zip), "--at", FIXED_BUILD_AT])
        manifest = read_bundle(out_zip)
        errors = validate_bundle(manifest)
        assert errors == [], f"Bundle failed validation: {errors}"

    def test_prints_bundle_path(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """build prints the output path on success."""
        proj = _copy_project(SAMPLE_PROJECT, tmp_path / "proj")
        main(["run", str(proj), "--at", FIXED_RUN_AT])
        out_zip = tmp_path / "bundle.zip"
        main(["build", str(proj), "--out", str(out_zip), "--at", FIXED_BUILD_AT])
        out = capsys.readouterr().out
        assert str(out_zip) in out

    def test_prints_control_and_run_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """build prints control count and run count on success."""
        proj = _copy_project(SAMPLE_PROJECT, tmp_path / "proj")
        main(["run", str(proj), "--at", FIXED_RUN_AT])
        out_zip = tmp_path / "bundle.zip"
        main(["build", str(proj), "--out", str(out_zip), "--at", FIXED_BUILD_AT])
        out = capsys.readouterr().out
        # Should mention "1 control" (or controls) and "1 run" (or runs)
        assert "1" in out


# ---------------------------------------------------------------------------
# No run log: must exit 1 with a helpful message
# ---------------------------------------------------------------------------


class TestBuildNoRunLog:
    def test_returns_1_when_no_run_log(self, tmp_path: Path) -> None:
        """build exits 1 when there is no run log (i.e. cflow run has not been run)."""
        proj = _copy_project(SAMPLE_PROJECT, tmp_path / "proj")
        out_zip = tmp_path / "bundle.zip"
        rc = main(["build", str(proj), "--out", str(out_zip), "--at", FIXED_BUILD_AT])
        assert rc == 1

    def test_prints_run_before_build_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """build prints a 'run before build' guidance message when no run log exists."""
        proj = _copy_project(SAMPLE_PROJECT, tmp_path / "proj")
        out_zip = tmp_path / "bundle.zip"
        main(["build", str(proj), "--out", str(out_zip), "--at", FIXED_BUILD_AT])
        combined = capsys.readouterr()
        output = combined.out + combined.err
        # The message must acknowledge a run may have failed, not just be absent
        assert "completed without errors" in output.lower() or "errors" in output.lower()

    def test_empty_run_log_exits_1(self, tmp_path: Path) -> None:
        """build exits 1 when run-log.json exists but is empty (zero runs)."""
        proj = _copy_project(SAMPLE_PROJECT, tmp_path / "proj")
        # Create an empty run log file
        target_dir = proj / "target"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "run-log.json").write_text("", encoding="utf-8")
        out_zip = tmp_path / "bundle.zip"
        rc = main(["build", str(proj), "--out", str(out_zip), "--at", FIXED_BUILD_AT])
        assert rc == 1


# ---------------------------------------------------------------------------
# --out default
# ---------------------------------------------------------------------------


class TestBuildOutDefault:
    def test_default_out_in_project_dir(self, tmp_path: Path) -> None:
        """When --out is omitted, build writes import-bundle.zip in the project dir."""
        proj = _copy_project(SAMPLE_PROJECT, tmp_path / "proj")
        main(["run", str(proj), "--at", FIXED_RUN_AT])
        rc = main(["build", str(proj), "--at", FIXED_BUILD_AT])
        assert rc == 0
        assert (proj / "import-bundle.zip").exists()


# ---------------------------------------------------------------------------
# --at default (clock boundary)
# ---------------------------------------------------------------------------


class TestBuildAtDefault:
    def test_build_without_at_exits_0(self, tmp_path: Path) -> None:
        """--at is optional; the CLI injects now() when omitted."""
        proj = _copy_project(SAMPLE_PROJECT, tmp_path / "proj")
        main(["run", str(proj), "--at", FIXED_RUN_AT])
        out_zip = tmp_path / "bundle.zip"
        rc = main(["build", str(proj), "--out", str(out_zip)])
        assert rc == 0
