from __future__ import annotations

import json

from controlflow_sdk.plane import fetch
from controlflow_sdk.store import repo
from controlflow_sdk.store.db import connect


def _fake_opener(payload):
    body = json.dumps(payload).encode()
    def opener(req):
        return body, "application/json"
    return opener


def test_create_from_url_snapshots_and_stores_fetch(client):
    # Inject a fake opener so no network is touched.
    client.app.state.fetch_opener = _fake_opener([{"id": "A", "amt": 5},
                                                  {"id": "B", "amt": 6}])
    resp = client.post("/sources/from-url", data={
        "source_id": "api", "url": "https://example.test/items.json",
        "headers": "", "record_path": "", "as_of_date": "2026-01-01",
    }, follow_redirects=False)
    assert resp.status_code in (302, 303)

    edit = client.get("/sources/api")
    assert "id" in edit.text and "amt" in edit.text
    conn = connect(client.app.state.project_root)
    src = repo.get_source(conn, "api")
    fetch_row = repo.get_source_fetch(conn, "api")
    conn.close()
    assert src["format"] == "csv"          # JSON snapshotted to CSV
    assert fetch_row["url"] == "https://example.test/items.json"
    # snapshot file exists on disk
    assert (client.app.state.project_root / src["path"]).is_file()


def test_from_url_form_shows_secrets_warning(client):
    page = client.get("/sources/from-url")
    assert "plaintext" in page.text.lower()
    assert "controlplane.db" in page.text


def test_fetch_error_rerenders_form(client):
    def boom(req):
        raise fetch.FetchError("Could not reach host")
    client.app.state.fetch_opener = boom
    resp = client.post("/sources/from-url", data={
        "source_id": "bad", "url": "https://nope.test/x.json",
        "headers": "", "record_path": "", "as_of_date": "",
    }, follow_redirects=False)
    assert resp.status_code == 200
    assert "Could not reach host" in resp.text
