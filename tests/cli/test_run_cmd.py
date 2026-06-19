"""Tests for the ``cflow run`` subcommand (store-backed)."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pytest

from controlflow_sdk.cli import main
from controlflow_sdk.cli.import_cmd import import_cmd
from controlflow_sdk.store import repo
from controlflow_sdk.store.db import connect

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "northwind-trading"

FIXED_AT = "2026-03-31T00:00:00+00:00"

# A single well-known control from the northwind example.
CONTROL_ID = "Finance.GL.1"


def _engagement(tmp_path: Path) -> Path:
    """Import the northwind example into an engagement dir and copy data files."""
    into = tmp_path / "eng"
    import_cmd(argparse.Namespace(src=str(EXAMPLE_DIR), into=str(into)))
    shutil.copytree(str(EXAMPLE_DIR / "data"), str(into / "data"))
    return into


# ---------------------------------------------------------------------------
# Happy-path: run all controls
# ---------------------------------------------------------------------------


class TestRunAll:
    def test_returns_0(self, tmp_path: Path) -> None:
        root = _engagement(tmp_path)
        rc = main(["run", str(root), "--at", FIXED_AT])
        assert rc == 0

    def test_creates_markdown_workpaper(self, tmp_path: Path) -> None:
        root = _engagement(tmp_path)
        main(["run", str(root), "--at", FIXED_AT])
        wp = root / "target" / "workpapers" / f"{CONTROL_ID}.md"
        assert wp.exists(), f"Expected {wp} to be created"
        assert wp.stat().st_size > 0

    def test_creates_html_workpaper(self, tmp_path: Path) -> None:
        root = _engagement(tmp_path)
        main(["run", str(root), "--at", FIXED_AT])
        wp = root / "target" / "workpapers" / f"{CONTROL_ID}.html"
        assert wp.exists(), f"Expected {wp} to be created"
        assert wp.stat().st_size > 0

    def test_html_starts_with_doctype(self, tmp_path: Path) -> None:
        root = _engagement(tmp_path)
        main(["run", str(root), "--at", FIXED_AT])
        html = (root / "target" / "workpapers" / f"{CONTROL_ID}.html").read_text()
        assert html.strip().lower().startswith("<!doctype html>")

    def test_creates_violations_json(self, tmp_path: Path) -> None:
        root = _engagement(tmp_path)
        main(["run", str(root), "--at", FIXED_AT])
        ev = root / "target" / "evidence" / f"{CONTROL_ID}-violations.json"
        assert ev.exists(), f"Expected {ev} to be created"

    def test_runs_persisted_to_store(self, tmp_path: Path) -> None:
        """Runs must be written to the SQLite store, not a run-log.json."""
        root = _engagement(tmp_path)
        main(["run", str(root), "--at", FIXED_AT])
        conn = connect(root)
        runs = repo.list_runs_for(conn, CONTROL_ID)
        assert runs, "Expected at least one run in the store for CONTROL_ID"

    def test_store_run_has_correct_executed_at(self, tmp_path: Path) -> None:
        root = _engagement(tmp_path)
        main(["run", str(root), "--at", FIXED_AT])
        conn = connect(root)
        runs = repo.list_runs_for(conn, CONTROL_ID)
        assert runs[0]["executed_at"] == FIXED_AT

    def test_prints_summary_line(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        root = _engagement(tmp_path)
        main(["run", str(root), "--at", FIXED_AT])
        out = capsys.readouterr().out
        assert CONTROL_ID in out


# ---------------------------------------------------------------------------
# --control filter
# ---------------------------------------------------------------------------


class TestRunSingleControl:
    def test_returns_0_for_known_control(self, tmp_path: Path) -> None:
        root = _engagement(tmp_path)
        rc = main(["run", str(root), "--control", CONTROL_ID, "--at", FIXED_AT])
        assert rc == 0

    def test_creates_workpaper_for_selected_control(self, tmp_path: Path) -> None:
        root = _engagement(tmp_path)
        main(["run", str(root), "--control", CONTROL_ID, "--at", FIXED_AT])
        wp = root / "target" / "workpapers" / f"{CONTROL_ID}.md"
        assert wp.exists()

    def test_returns_1_for_unknown_control(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        root = _engagement(tmp_path)
        rc = main(["run", str(root), "--control", "does_not_exist", "--at", FIXED_AT])
        assert rc == 1

    def test_unknown_control_prints_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        root = _engagement(tmp_path)
        main(["run", str(root), "--control", "does_not_exist", "--at", FIXED_AT])
        out = capsys.readouterr()
        combined = out.out + out.err
        assert "does_not_exist" in combined


# ---------------------------------------------------------------------------
# --at default (clock boundary)
# ---------------------------------------------------------------------------


class TestAtDefault:
    def test_run_without_at_still_exits_0(self, tmp_path: Path) -> None:
        """--at is optional; the CLI injects now() when omitted."""
        root = _engagement(tmp_path)
        rc = main(["run", str(root)])
        assert rc == 0

    def test_run_without_at_creates_workpaper(self, tmp_path: Path) -> None:
        root = _engagement(tmp_path)
        main(["run", str(root)])
        wp = root / "target" / "workpapers" / f"{CONTROL_ID}.md"
        assert wp.exists()
