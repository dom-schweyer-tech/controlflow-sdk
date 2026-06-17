"""``cflow build`` subcommand — assemble a versioned import-bundle zip.

Usage
-----
    cflow build [dir] [--out import-bundle.zip] [--at <iso8601>]

Steps
-----
1. Load the project from *dir*.
2. Read ``target/run-log.json`` via ``read_runs``.
3. Exit 1 with a "run before build" message when no runs are found.
4. Group runs by ``control_id``.
5. Call ``assemble_bundle(project, runs_by_control, generated_at)`` to build a
   validated manifest dict.
6. Call ``write_bundle(manifest, target_dir, out_path)`` to write the zip.
7. Print the bundle path plus control/run counts on success.

Exit codes
----------
0  Bundle written successfully.
1  No runs found, bundle validation failed, or project failed to load.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

from controlflow_sdk.bundle import BundleError, assemble_bundle, write_bundle
from controlflow_sdk.project.discovery import Project
from controlflow_sdk.runner.runlog import read_runs


def build_cmd(args: argparse.Namespace) -> int:
    """Handle ``cflow build [dir] [--out <path>] [--at <iso8601>]``."""
    root = Path(args.dir).resolve()
    generated_at: str = args.at
    out_path = Path(args.out) if args.out else root / "import-bundle.zip"

    # ── Load project ──────────────────────────────────────────────────────────
    try:
        project = Project.load(root)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR loading project at {root}: {exc}", file=sys.stderr)
        return 1

    # ── Read run log ──────────────────────────────────────────────────────────
    target_dir = root / "target"
    runs = read_runs(target_dir)

    if not runs:
        print(
            "ERROR: No runs found in target/run-log.json — run `cflow run` first, "
            "and make sure it completed without errors.",
            file=sys.stderr,
        )
        return 1

    # ── Group runs by control_id ───────────────────────────────────────────────
    runs_by_control: dict[str, list[dict]] = defaultdict(list)
    for run in runs:
        control_id = run.get("control_id", "")
        if control_id:
            runs_by_control[control_id].append(run)
        else:
            print(
                f"warning: skipping run with no control_id: {run.get('run_id', '?')}",
                file=sys.stderr,
            )

    total_runs = sum(len(v) for v in runs_by_control.values())
    control_count = len(runs_by_control)

    # ── Assemble and write bundle ──────────────────────────────────────────────
    try:
        manifest = assemble_bundle(project, dict(runs_by_control), generated_at)
    except BundleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_bundle(manifest, target_dir, out_path)

    # ── Summary ────────────────────────────────────────────────────────────────
    ctrl_word = "control" if control_count == 1 else "controls"
    run_word = "run" if total_runs == 1 else "runs"
    print(f"  BUNDLE  {out_path}  {control_count} {ctrl_word} / {total_runs} {run_word}")

    return 0
