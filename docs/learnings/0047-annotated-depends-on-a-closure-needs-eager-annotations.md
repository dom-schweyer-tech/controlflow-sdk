---
id: 0047
date: 2026-06-29
area: backend
tags: [fastapi, annotated, future-annotations, dependency-injection, sonarqube]
status: active
supersedes:
superseded_by:
---

# Don't put a closure-injected `Depends` inside `Annotated[...]` while a module has `from __future__ import annotations`

## Context
The route modules use the `register(app, templates, get_conn)` plugin shape, so the DI
callable `get_conn` is a **closure variable** (a `register` parameter), not a module
global. Migrating the conn dependency to the modern `Annotated` form to satisfy SonarQube
`python:S8410` — `conn: sqlite3.Connection = Depends(get_conn)` →
`conn: Annotated[sqlite3.Connection, Depends(get_conn)]` — silently broke injection:
**every page returned `422` with `{"loc":["query","conn"]}`**, FastAPI treating `conn` as
a required query param. `ruff`, `mypy`, and import all passed; only running the app (or
`TestClient`) revealed it.

Root cause: with `from __future__ import annotations` the annotation is a **string**.
FastAPI resolves it via `get_type_hints`, which looks names up in the function's
`__globals__` — and the closure `get_conn` is **not** there, so the `Depends` marker
inside `Annotated[...]` is lost and the param degrades to a plain query field. The old
default-value form worked because `Depends(get_conn)` is a real runtime object built at
function-definition time (capturing the closure), read directly from the signature
defaults — never re-resolved from a string.

## What worked
Dropping `from __future__ import annotations` from the route modules. The `Annotated[...,
Depends(get_conn)]` annotation then evaluates **eagerly** at def time, capturing the
closure as a real object, so FastAPI sees the `Depends`. Runtime-safe because the floor is
`>=3.11` (PEP 604 `X | None`, `list[str]`, etc. all evaluate at runtime). Verified by the
full `tests/plane` suite going green (126 failures → 0) plus the e2e browser smoke.

## The rule
- A FastAPI dependency injected via a **closure variable** (e.g. the `register(app,
  templates, get_conn)` plugin shape) MUST NOT be moved into an `Annotated[T,
  Depends(closure_var)]` hint **while that module keeps `from __future__ import
  annotations`** — stringized annotations make FastAPI's `get_type_hints` unable to
  resolve the closure name, and the param silently degrades to a query param (`422`,
  `loc:["query","<name>"]`). Either keep the default-value form (`x: T =
  Depends(closure_var)`), or remove `from __future__ import annotations` from that module
  so the annotation evaluates eagerly and captures the closure. Markers that reference a
  **module-global** name (`Query()`, `Form()`, `Path()`, `File()`, `Depends(module_func)`)
  are safe inside `Annotated[...]` even when stringized, because `get_type_hints` resolves
  them from `__globals__`.
- Any change to a route's parameter declaration (DI form, `Annotated` migration, param
  reordering) is **only** proven by exercising the route (`TestClient`/e2e), never by
  `ruff`/`mypy`/import — all three pass while injection is silently broken.

## Reference
- `uticen_lite/plane/routes/*.py` (no `from __future__ import annotations`; `Annotated`
  DI), `uticen_lite/plane/app.py` (the positional `*.register(app, templates, get_conn)`
  calls), `tests/plane/conftest.py` (`TestClient(create_app(...))`).
- Related: [[0002]] (the per-handler `Depends(get_conn)` connection pattern).
- PR #130 (the maintainability sweep where this surfaced).
