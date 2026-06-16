"""Control discovery and test.py loading for ControlFlow SDK projects.

Walks a project root for ``controls/*/control.yaml`` files, validates and
parses each one into a :class:`~controlflow_sdk.model.control.ControlDef`,
resolves source references against the project's ``sources.yaml``, and
provides a loader that imports each control's ``test.py`` and returns the
``test`` callable.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from controlflow_sdk.model.control import (
    ControlDef,
    FrameworkRefs,
    RiskRef,
    SourceBinding,
)
from controlflow_sdk.project.loader import (
    ProjectConfig,
    ProjectError,
    load_project_config,
    load_sources,
)
from controlflow_sdk.schema.validate import validate_control


def _parse_control(
    doc: dict[str, Any],
    sources_map: dict[str, SourceBinding],
    control_dir: Path,
) -> ControlDef:
    """Build a :class:`ControlDef` from a validated control document.

    A private ``_test_file`` attribute (absolute :class:`~pathlib.Path`) is
    attached to the returned instance so that :func:`load_test_callable` can
    locate the script without needing the project root again.

    Args:
        doc:         Parsed YAML dict for the control.
        sources_map: All project sources keyed by id.
        control_dir: Directory that contains ``control.yaml`` (used to resolve
                     ``test_path`` for later import).

    Returns:
        A fully populated :class:`ControlDef` with ``_test_file`` set.

    Raises:
        ProjectError: If a source id referenced in ``sources:`` is not present
                      in *sources_map*.
    """
    # Resolve source references
    resolved_sources: list[SourceBinding] = []
    for src_ref in doc.get("sources", []):
        src_id = src_ref["id"]
        if src_id not in sources_map:
            raise ProjectError(
                f"Control '{doc.get('id')}' references unknown source '{src_id}'. "
                f"Available sources: {sorted(sources_map)}"
            )
        resolved_sources.append(sources_map[src_id])

    # Parse framework_refs — make a copy so we don't mutate the doc
    fr_raw: dict[str, Any] = dict(doc.get("framework_refs") or {})
    nist: list[str] = list(fr_raw.pop("nist", []))
    extra: dict[str, list[str]] = {k: list(v) for k, v in fr_raw.items()}
    framework_refs = FrameworkRefs(nist=nist, extra=extra)

    # Parse optional risk block
    risk_raw = doc.get("risk")
    risk: RiskRef | None = None
    if risk_raw is not None:
        risk = RiskRef(
            name=risk_raw["name"],
            description=risk_raw.get("description", ""),
            inherent_rating=risk_raw.get("inherent_rating"),
        )

    test_path: str = doc.get("test_path", "test.py")

    control = ControlDef(
        id=doc["id"],
        title=doc["title"],
        objective=doc["objective"],
        narrative=doc.get("narrative", ""),
        framework_refs=framework_refs,
        risk=risk,
        sources=resolved_sources,
        test_path=test_path,
        severity_policy=dict(doc.get("severity_policy") or {}),
    )
    # Attach the absolute test file path as a private attribute so that
    # load_test_callable can find the script without the project root.
    # We use setattr to avoid a mypy "unexpected attribute" error on the
    # dataclass; the attribute is intentionally out-of-band.
    setattr(control, "_test_file", control_dir / test_path)
    return control


def discover_controls(root: Path) -> list[ControlDef]:
    """Walk ``<root>/controls/*/control.yaml`` and return parsed controls.

    Each control is validated against the JSON schema, then its ``sources:``
    entries are resolved against ``<root>/sources.yaml``.  The ``test_path``
    field is stored as declared (relative to the control directory) for use by
    :func:`load_test_callable`.

    Args:
        root: Path to the project root directory (must contain ``sources.yaml``
              and a ``controls/`` subtree).

    Returns:
        List of :class:`~controlflow_sdk.model.control.ControlDef` instances,
        one per discovered ``control.yaml``.

    Raises:
        FileNotFoundError: If ``sources.yaml`` is missing.
        ProjectError:
            - If any ``control.yaml`` fails schema validation.
            - If a control references a source id not defined in ``sources.yaml``.
    """
    sources_map = load_sources(root)
    controls_root = root / "controls"
    results: list[ControlDef] = []

    if not controls_root.is_dir():
        return results

    for control_yaml in sorted(controls_root.glob("*/control.yaml")):
        with control_yaml.open(encoding="utf-8") as fh:
            doc: dict[str, Any] = yaml.safe_load(fh) or {}

        errors = validate_control(doc)
        if errors:
            msg = f"{control_yaml} failed schema validation:\n" + "\n".join(
                f"  - {e}" for e in errors
            )
            raise ProjectError(msg)

        control_def = _parse_control(doc, sources_map, control_yaml.parent)
        results.append(control_def)

    return results


def load_test_callable(control: ControlDef) -> Callable[..., list[Any]]:
    """Import a control's ``test.py`` and return its ``test`` function.

    The function is imported via :func:`importlib.util.spec_from_file_location`
    so it does **not** need to be on ``sys.path``.  The ``test`` callable is
    returned as-is; it is **not** executed.

    Args:
        control: A :class:`~controlflow_sdk.model.control.ControlDef` whose
                 ``test_path`` points to the script relative to the directory
                 inferred from ``control.yaml``'s location.  The full absolute
                 path is reconstructed from the control's id convention
                 (``controls/<id>/test.py`` under the project root) using the
                 path stored at import time.

    Returns:
        The ``test`` callable from the control's ``test.py``.

    Raises:
        ProjectError: If ``test.py`` is missing, if ``test`` is not defined in
                      it, or if ``test`` is not callable.
    """
    # Resolve the test file path.  ``control._test_file`` is set by
    # discover_controls; fall back to reconstructing from test_path if this
    # control was built manually.
    test_file: Path | None = getattr(control, "_test_file", None)
    if test_file is None:
        raise ProjectError(
            f"Control '{control.id}' has no _test_file path. "
            "Use discover_controls() to load controls."
        )

    if not test_file.exists():
        raise ProjectError(f"Control '{control.id}': test file not found at {test_file}")

    module_name = f"controlflow_sdk._tests.{control.id}"
    spec = importlib.util.spec_from_file_location(module_name, test_file)
    if spec is None or spec.loader is None:
        raise ProjectError(f"Control '{control.id}': could not create module spec from {test_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    fn = getattr(module, "test", None)
    if fn is None:
        raise ProjectError(f"Control '{control.id}': test.py at {test_file} has no 'test' function")
    if not callable(fn):
        raise ProjectError(
            f"Control '{control.id}': 'test' in {test_file} is not callable "
            f"(got {type(fn).__name__})"
        )
    return fn  # type: ignore[return-value]


@dataclass
class Project:
    """A fully loaded ControlFlow project.

    Attributes:
        config:   Parsed ``cflow.yaml`` configuration.
        sources:  Data source bindings keyed by source id.
        controls: Discovered and parsed control definitions.
    """

    config: ProjectConfig
    sources: dict[str, SourceBinding]
    controls: list[ControlDef]

    @classmethod
    def load(cls, root: Path) -> Project:
        """Load a complete project from *root*.

        Orchestrates :func:`load_project_config`, :func:`load_sources`, and
        :func:`discover_controls` in order.

        Args:
            root: Path to the project root directory.

        Returns:
            A :class:`Project` instance with all fields populated.

        Raises:
            FileNotFoundError: If ``cflow.yaml`` or ``sources.yaml`` are absent.
            ProjectError: If any validation error is encountered.
        """
        config = load_project_config(root)
        sources = load_sources(root)
        controls = discover_controls(root)
        return cls(config=config, sources=sources, controls=controls)
