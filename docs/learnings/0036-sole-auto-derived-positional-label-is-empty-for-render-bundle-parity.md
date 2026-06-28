---
id: 0036
date: 2026-06-28
area: contract
tags: [render, bundle, procedures, byte-identity, parity]
status: active
supersedes: null
superseded_by: null
---

# Auto-derive a positional label (P1..Pn) only when ≥2 items exist; a SOLE auto-derived item carries an EMPTY label so the render stays byte-identical and matches the bundle's single-item default

## Context

Procedures carry a `code` (P1, P2, …). A legacy control with no defined procedures derives
ONE auto procedure at read/run time. The workpaper heading keys off `if proc.code:` —
`{code} · {title}` when a code is present, else the historical `P{i}: {title}`. The bundle's
single-procedure assemble path hardcodes `code=""`.

## What went wrong

- Assigning the lone auto procedure `code="P1"` changed the single-procedure workpaper
  heading from `P1: {title}` to `P1 · {title}` — silently altering existing single-control
  output and breaking the "N≤1 byte-identical" guarantee.
- It also made the **local render** (code `"P1"`) disagree with the **exported bundle**
  (single-procedure path emits `code=""`): the audit file the app shows would differ from the
  workpaper rendered locally for the same control.
- No test pinned single-procedure heading byte-identity, so the suite stayed green.

## The rule

- When auto-deriving a **positional** label (P1..Pn) for a grouping that is **also serialized
  into the bundle**, assign the positional label only when **≥2** items exist; a **sole**
  auto-derived item gets an **empty** label. This keeps the single-item render byte-identical
  to the pre-feature form AND matches the bundle's single-item default (empty label).
- Author-**defined** labels always keep their own value (only the AUTO path, and only when it
  is the lone item, is forced empty).
- A lone auto-numbered label silently changes existing single-item output and makes the local
  render disagree with the exported bundle — pin it with a test asserting the sole item's
  label is empty AND the single-item render uses the legacy (no-prefix) form.

## Reference

- `controlflow_sdk/pipeline/procedures.py` — `_auto_procedure` / `effective_procedures`
  (the `lone` branch that forces `code=""`).
- `controlflow_sdk/render/html.py` — `_emit_procedures` (`if proc.code:` heading branch);
  `controlflow_sdk/bundle/assemble.py` — single-procedure path (`code=""`).
- Keeps the bundle and the local workpaper in parity ([[0001]] cardinal); verdict/threshold
  stay out of the bundle ([[0015]]).
