"""Render a Workpaper to a self-contained HTML document.

Rules:
- Starts with ``<!doctype html>``.
- Inline ``<style>`` only — no external assets, no ``<link rel="stylesheet">``.
- No ``<script>`` tags anywhere.
- ALL author/data-derived text passed through ``html.escape`` to prevent XSS.
- Pure stdlib; Pyodide-safe.
"""

from __future__ import annotations

import html as _html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from controlflow_sdk.model.workpaper import Workpaper

# ---------------------------------------------------------------------------
# Inline stylesheet (dark enterprise palette matching ControlFlow's UI)
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #0b0d17;
  color: #e2e8f0;
  line-height: 1.6;
  padding: 2rem;
}
h1 { font-size: 1.75rem; color: #f8fafc; margin-bottom: 0.5rem; }
h2 {
  font-size: 1.25rem; color: #94a3b8; margin: 2rem 0 0.5rem;
  border-bottom: 1px solid #1e293b; padding-bottom: 0.25rem;
}
h3 { font-size: 1rem; color: #cbd5e1; margin: 1rem 0 0.5rem; }
p { margin: 0.5rem 0; color: #cbd5e1; }
.meta { color: #64748b; font-size: 0.875rem; margin-bottom: 0.25rem; }
.ref-tag {
  display: inline-block;
  background: #1e40af;
  color: #bfdbfe;
  border-radius: 4px;
  padding: 0.1rem 0.4rem;
  font-size: 0.75rem;
  margin: 0.1rem;
}
pre {
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 1rem;
  overflow-x: auto;
  font-family: "SF Mono", "Fira Code", "Consolas", monospace;
  font-size: 0.85rem;
  color: #7dd3fc;
  margin: 0.5rem 0;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 0.75rem 0;
  font-size: 0.875rem;
}
th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  background: #1e293b;
  color: #94a3b8;
  font-weight: 600;
  border-bottom: 1px solid #334155;
}
td {
  padding: 0.45rem 0.75rem;
  border-bottom: 1px solid #1e293b;
  color: #cbd5e1;
}
tr:last-child td { border-bottom: none; }
.severity-critical { color: #f87171; font-weight: 600; }
.severity-high     { color: #fb923c; font-weight: 600; }
.severity-medium   { color: #fbbf24; }
.severity-low      { color: #34d399; }
.mono { font-family: "SF Mono", "Fira Code", monospace; font-size: 0.8rem; color: #7dd3fc; }
.prov-block {
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 0.75rem 1rem;
  margin: 0.5rem 0;
  font-size: 0.85rem;
}
.prov-block dt { color: #64748b; display: inline; }
.prov-block dd { display: inline; color: #cbd5e1; margin-left: 0.25rem; }
.prov-entry { margin-bottom: 0.5rem; }
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _e(text: object) -> str:
    """html.escape any value (converts to str first)."""
    return _html.escape(str(text))


def _severity_class(severity: str) -> str:
    key = severity.lower()
    mapping = {
        "critical": "severity-critical",
        "high": "severity-high",
        "medium": "severity-medium",
        "low": "severity-low",
    }
    return mapping.get(key, "")


# ---------------------------------------------------------------------------
# Public renderer
# ---------------------------------------------------------------------------


def render_html(wp: Workpaper) -> str:
    """Return a self-contained HTML document for *wp*.

    Guarantee: no ``<script`` tags; all author/data text is html-escaped.
    """
    parts: list[str] = []

    def emit(s: str = "") -> None:
        parts.append(s)

    emit("<!doctype html>")
    emit('<html lang="en">')
    emit("<head>")
    emit('<meta charset="utf-8">')
    emit('<meta name="viewport" content="width=device-width, initial-scale=1">')
    emit(f"<title>{_e(wp.title)} — Audit Workpaper</title>")
    emit(f"<style>{_CSS}</style>")
    emit("</head>")
    emit("<body>")

    # ── Title + metadata ──────────────────────────────────────────────────────
    emit(f"<h1>{_e(wp.title)}</h1>")
    emit(f'<p class="meta">Control ID: <span class="mono">{_e(wp.control_id)}</span></p>')
    emit(f'<p class="meta">Generated: {_e(wp.generated_at)}</p>')

    # ── Objective ─────────────────────────────────────────────────────────────
    emit("<h2>Objective</h2>")
    emit(f"<p>{_e(wp.objective)}</p>")

    # ── Narrative ─────────────────────────────────────────────────────────────
    emit("<h2>Narrative</h2>")
    emit(f"<p>{_e(wp.narrative)}</p>")

    # ── Framework References ───────────────────────────────────────────────────
    emit("<h2>Framework References</h2>")
    nist_refs: list[str] = wp.framework_refs.get("nist", [])
    extra: dict[str, list[str]] = wp.framework_refs.get("extra", {})
    if nist_refs or extra:
        emit("<p>")
        if nist_refs:
            for ref in nist_refs:
                emit(f'<span class="ref-tag">{_e(ref)}</span>')
        for framework, refs in extra.items():
            for ref in refs:
                emit(f'<span class="ref-tag">{_e(framework)}: {_e(ref)}</span>')
        emit("</p>")
    else:
        emit("<p>None</p>")

    # ── Procedures ────────────────────────────────────────────────────────────
    for i, proc in enumerate(wp.procedures, start=1):
        run = proc.result
        emit(f"<h2>Procedure {i}: {_e(proc.title)}</h2>")

        # Narrative
        emit("<h3>Narrative</h3>")
        emit(f"<p>{_e(proc.narrative)}</p>")

        # Test code
        emit("<h3>Test</h3>")
        emit(f"<pre>{_e(proc.test_code)}</pre>")

        # Results table
        emit("<h3>Results</h3>")
        emit("<table>")
        emit("<thead><tr><th>Metric</th><th>Value</th></tr></thead>")
        emit("<tbody>")
        emit(f"<tr><td>Population</td><td>{_e(run.population_size)}</td></tr>")
        emit(f"<tr><td>Passed</td><td>{_e(run.passed)}</td></tr>")
        emit(f"<tr><td>Failed</td><td>{_e(run.failed)}</td></tr>")
        emit(f"<tr><td>Pass Rate</td><td>{_e(run.pass_rate)}%</td></tr>")
        emit("</tbody></table>")

        # Violations table
        if run.violations:
            emit("<h3>Violations</h3>")
            emit("<table>")
            emit("<thead><tr><th>Item Key</th><th>Severity</th><th>Description</th></tr></thead>")
            emit("<tbody>")
            for v in run.violations:
                sev_cls = _severity_class(str(v.severity))
                emit(
                    f"<tr>"
                    f'<td class="mono">{_e(v.item_key)}</td>'
                    f'<td class="{_e(sev_cls)}">{_e(v.severity)}</td>'
                    f"<td>{_e(v.description)}</td>"
                    f"</tr>"
                )
            emit("</tbody></table>")

        # Provenance
        if run.provenance:
            emit("<h3>Data Provenance</h3>")
            for prov in run.provenance:
                emit('<div class="prov-block prov-entry">')
                emit(f'<dl><dt>Source:</dt> <dd class="mono">{_e(prov.path)}</dd><br>')
                emit(f'<dt>SHA-256:</dt> <dd class="mono">{_e(prov.sha256)}</dd><br>')
                emit(f"<dt>Row count:</dt> <dd>{_e(prov.row_count)}</dd></dl>")
                emit("</div>")

    emit("</body>")
    emit("</html>")

    return "\n".join(parts)
