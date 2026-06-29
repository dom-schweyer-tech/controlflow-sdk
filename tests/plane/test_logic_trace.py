"""Route tests for the Logic ▸ Trace single-record trace (issue #29)."""
from __future__ import annotations

import io
import json

from uticen_lite.store import repo


def _make_source(client, sid, csv_bytes: bytes) -> None:
    client.post(
        "/sources",
        data={"source_id": sid, "format": "csv"},
        files={"file": (f"{sid}.csv", io.BytesIO(csv_bytes), "text/csv")},
        follow_redirects=False,
    )


def _conn(client):
    from uticen_lite.store.db import connect
    return connect(client.app.state.project_root)


def _set_key(client, sid, key_col) -> None:
    conn = _conn(client)
    try:
        src = repo.get_source(conn, sid)
        cols = [{**c, "is_key": (c["original_name"] == key_col)} for c in src["columns"]]
        repo.set_columns(conn, sid, cols)
    finally:
        conn.close()


def _make_control(client, cid="C1") -> None:
    client.post("/controls", data={
        "id": cid, "title": "Trace Test", "objective": "o", "narrative": "n",
    }, follow_redirects=False)


def _save_pipeline(client, cid, graph):
    return client.post(f"/controls/{cid}/logic/builder",
                       data={"pipeline_json": json.dumps(graph)},
                       follow_redirects=False)


_INVOICES = (
    b"invoice_id,amount\n"
    b"INV001,100\nINV002,200\nINV003,300\nINV004,400\nINV005,500\n"
)


def _seeded(client, conditions=None):
    _make_source(client, "invoices", _INVOICES)
    _set_key(client, "invoices", "invoice_id")
    cid = "TR1"
    _make_control(client, cid)
    graph = {"nodes": [
        {"id": "imp", "type": "import", "source_id": "invoices", "inputs": []},
        {"id": "tst", "type": "test", "inputs": ["imp"], "config": {
            "logic": "all",
            "conditions": conditions if conditions is not None
            else [{"column": "amount", "op": "gt", "value": 100}],
        }},
    ]}
    _save_pipeline(client, cid, graph)
    return client, cid


def test_trace_tab_is_linked_on_builder(client):
    c, cid = _seeded(client)
    r = c.get(f"/controls/{cid}/logic/builder")
    assert r.status_code == 200
    assert f"/controls/{cid}/logic/trace" in r.text


def test_trace_picker_shows_example_keys(client):
    c, cid = _seeded(client)
    r = c.get(f"/controls/{cid}/logic/trace")
    assert r.status_code == 200
    assert "INV001" in r.text  # an example-key chip


def test_flagged_record_renders_flagged_and_condition(client):
    c, cid = _seeded(client)
    r = c.get(f"/controls/{cid}/logic/trace", params={"key": "INV005"})
    assert r.status_code == 200
    assert "Flagged as an exception" in r.text
    assert "amount" in r.text and "gt" in r.text


def test_passing_record_renders_passed(client):
    c, cid = _seeded(client)
    r = c.get(f"/controls/{cid}/logic/trace", params={"key": "INV001"})
    assert r.status_code == 200
    assert "Passed" in r.text


def test_missing_key_renders_not_found(client):
    c, cid = _seeded(client)
    r = c.get(f"/controls/{cid}/logic/trace", params={"key": "ZZZ"})
    assert r.status_code == 200
    assert "No record" in r.text


def test_python_control_degrades(client):
    _make_source(client, "invoices", _INVOICES)
    _set_key(client, "invoices", "invoice_id")
    cid = "PYC"
    _make_control(client, cid)
    c = client
    # Bind the source, then author raw Python via the python tab.
    _save_pipeline(c, cid, {"nodes": [
        {"id": "imp", "type": "import", "source_id": "invoices", "inputs": []},
        {"id": "tst", "type": "test", "inputs": ["imp"],
         "config": {"logic": "all", "conditions": []}},
    ]})
    c.post(f"/controls/{cid}/logic/convert", follow_redirects=False)
    r = c.get(f"/controls/{cid}/logic/trace", params={"key": "INV001"})
    assert r.status_code == 200
    assert "rule builder" in r.text


def test_bad_condition_column_never_500s(client):
    c, cid = _seeded(client, conditions=[{"column": "nope", "op": "gt", "value": 1}])
    r = c.get(f"/controls/{cid}/logic/trace", params={"key": "INV001"})
    assert r.status_code == 200  # never 500 (learnings 0013/0033)
