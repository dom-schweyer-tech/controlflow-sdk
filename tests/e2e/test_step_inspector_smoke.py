"""Browser smoke: click a step count → drawer opens → table visible → download link present.

Opt-in test (the ``browser`` marker is excluded from the fast unit lane via
``addopts = "--ignore=tests/e2e"`` in pyproject.toml).  CI runs it via:

    pytest tests/e2e -m browser

after ``playwright install chromium``.

Fixtures used:
- ``live_server`` (str base URL) — from ``tests/e2e/conftest.py``: a real
  uvicorn server on a free port, torn down after the test.
- ``page`` (playwright.sync_api.Page) — from pytest-playwright.

Seeding is done via Playwright's ``page.request.post`` against ``live_server``
(no separate test-client import needed — keeps fixture deps minimal).
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

# Source CSV: two rows, so the Import step has row count 2 (shown as the
# clickable badge on the node card).
_CSV = b"user_id,can_create\nU1,true\nU2,false\n"


def _seed(page: Page, base: str) -> str:
    """POST source + control + pipeline + run via the live API; return the
    control id."""
    # Upload source.
    page.request.post(
        f"{base}/sources",
        multipart={
            "source_id": "users_insp",
            "format": "csv",
            "file": {
                "name": "users_insp.csv",
                "mimeType": "text/csv",
                "buffer": _CSV,
            },
        },
    )

    # Create control.
    page.request.post(
        f"{base}/controls",
        form={
            "id": "insp_ctrl",
            "title": "Inspector smoke",
            "objective": "o",
            "narrative": "n",
            "source_ids": "users_insp",
            "failure_threshold_count": "0",
        },
    )

    # Save a pipeline: Import(users_insp) → Filter → Test.
    # The Filter node is non-terminal, so its step count badge is what we click.
    graph = {
        "nodes": [
            {"id": "imp", "type": "import", "source_id": "users_insp"},
            {
                "id": "flt",
                "type": "filter",
                "inputs": ["imp"],
                "config": {
                    "logic": "all",
                    "conditions": [{"column": "can_create", "op": "not_empty"}],
                },
            },
            {
                "id": "tst",
                "type": "test",
                "inputs": ["flt"],
                "config": {
                    "logic": "all",
                    "severity": "high",
                    "item_key_column": "user_id",
                    "description_template": "User {user_id}",
                    "conditions": [
                        {"column": "can_create", "op": "eq", "value": "true"}
                    ],
                },
            },
        ]
    }
    page.request.post(
        f"{base}/controls/insp_ctrl/logic/builder",
        form={"pipeline_json": json.dumps(graph)},
    )

    # Run the control so step row counts are computed and the inspector has data.
    page.request.post(f"{base}/controls/insp_ctrl/run")

    return "insp_ctrl"


@pytest.mark.browser
def test_step_inspector_drawer(page: Page, live_server: str) -> None:
    """Click a step count badge → HTMX loads the drawer → table + download link visible."""
    base = live_server
    cid = _seed(page, base)

    # Navigate to the Logic ▸ Builder page for the seeded control.
    page.goto(f"{base}/controls/{cid}/logic/builder")

    # The pipe-count-btn is only rendered when node.count is not None (i.e.,
    # after a run).  Click the first visible one (the Import node's badge).
    count_btn = page.locator(".pipe-count-btn").first
    expect(count_btn).to_be_visible()
    count_btn.click()

    # HTMX swaps the drawer content into #step-drawer.  Wait for the step-panel
    # to appear (the drawer partial renders a <div class="step-panel card">).
    step_panel = page.locator("#step-drawer .step-panel")
    step_panel.wait_for(state="visible")

    # The drawer must contain a data table.
    expect(step_panel.locator("table")).to_have_count(1)

    # The drawer must show the "Download this step" export link.
    # The exact link text in _step_data.html is "Download this step (.xlsx)".
    expect(step_panel.get_by_text("Download this step", exact=False)).to_have_count(1)
