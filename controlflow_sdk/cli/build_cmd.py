"""``cflow build`` subcommand — assemble a versioned import-bundle zip.

Usage
-----
    cflow build [dir] [--out import-bundle.zip] [--at <iso8601>]

Steps
-----
1. Load the project from ``controlplane.db`` (via ``load_project_from_store``).
2. Read runs from the store (``repo.list_runs_for`` per control).
3. Exit 1 with a "run before build" message when no runs are found.
4. Reconstruct ``RunRecord.to_dict()`` shapes via ``_to_run_dicts`` for bundle parity.
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
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

from controlflow_sdk.bundle import BundleError, assemble_bundle, write_bundle
from controlflow_sdk.store import repo
from controlflow_sdk.store.db import connect
from controlflow_sdk.store.loader import load_project_from_store


def _to_run_dicts(runs_by_control: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Reconstruct ``RunRecord.to_dict()`` shapes from stored run dicts.

    The store returns raw dicts; this helper re-instantiates
    :class:`~controlflow_sdk.model.run.RunRecord` objects (with their derived
    properties) so the bundle receives exactly the same shape as the old
    ``run-log.json`` path produced.
    """
    from controlflow_sdk.model.run import RunRecord, SourceProvenance
    from controlflow_sdk.model.violation import Violation

    out: dict[str, list[dict]] = {}
    for cid, runs in runs_by_control.items():
        rebuilt = []
        for r in runs:
            rr = RunRecord(
                control_id=r["control_id"],
                executed_at=r["executed_at"],
                population_size=r["population_size"],
                violations=[Violation.from_raw(v) for v in r["violations"]],
                provenance=[SourceProvenance(**p) for p in r["provenance"]],
            )
            rebuilt.append(rr.to_dict())
        out[cid] = rebuilt
    return out


def build_cmd(args: argparse.Namespace) -> int:
    """Handle ``cflow build [dir] [--out <path>] [--at <iso8601>]``."""
    root = Path(args.dir).resolve()
    generated_at: str = args.at
    out_path = Path(args.out) if args.out else root / "import-bundle.zip"

    # ── Load project from store ────────────────────────────────────────────────
    try:
        conn = connect(root)
        project = load_project_from_store(conn)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR loading project at {root}: {exc}", file=sys.stderr)
        return 1

    # ── Read runs from store ───────────────────────────────────────────────────
    runs_by_control = {c.id: repo.list_runs_for(conn, c.id) for c in project.controls}
    runs_by_control = {cid: runs for cid, runs in runs_by_control.items() if runs}

    if not runs_by_control:
        print(
            "ERROR: No runs found in store — run `cflow run` first, "
            "and make sure it completed without errors.",
            file=sys.stderr,
        )
        return 1

    total_runs = sum(len(v) for v in runs_by_control.values())
    control_count = len(runs_by_control)

    # ── Assemble and write bundle ──────────────────────────────────────────────
    target_dir = root / "target"
    try:
        manifest = assemble_bundle(project, _to_run_dicts(runs_by_control), generated_at)
    except BundleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_bundle(manifest, target_dir, out_path)

    # ── Summary ────────────────────────────────────────────────────────────────
    ctrl_word = "control" if control_count == 1 else "controls"
    run_word = "run" if total_runs == 1 else "runs"
    print(f"  BUNDLE  {out_path}  {control_count} {ctrl_word} / {total_runs} {run_word}")

    return 0
