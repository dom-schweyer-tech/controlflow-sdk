import io

from controlflow_sdk.store import repo
from controlflow_sdk.store.db import connect


def _src(client):
    csv = b"user_id,can_create,can_approve\nU1,true,true\n"
    client.post("/sources", data={"source_id": "users", "format": "csv"},
                files={"file": ("users.csv", io.BytesIO(csv), "text/csv")},
                follow_redirects=False)


def test_rule_builder_builds_spec_from_conditions(client):
    _src(client)
    client.post("/controls", data={
        "id": "sod", "title": "SoD", "objective": "o", "narrative": "n",
        "test_kind": "rule", "rule_logic": "all", "rule_severity": "high",
        "rule_description": "User {user_id} can create and approve",
        "rule_item_key": "user_id",
        "cond_column": ["can_create", "can_approve"],
        "cond_op": ["eq", "eq"],
        "cond_value": ["true", "true"],
        "source_ids": ["users"],
    }, follow_redirects=False)
    c = repo.get_control(connect(client.app.state.project_root), "sod")
    assert c["test_kind"] == "rule"
    spec = c["rule_spec"]
    assert spec["logic"] == "all" and spec["severity"] == "high"
    assert spec["conditions"] == [
        {"column": "can_create", "op": "eq", "value": True},
        {"column": "can_approve", "op": "eq", "value": True},
    ]
    assert spec["item_key_column"] == "user_id"


def test_add_condition_row_partial(client):
    resp = client.get("/controls/_condition_row")
    assert resp.status_code == 200
    assert 'name="cond_column"' in resp.text
    assert 'name="cond_op"' in resp.text
