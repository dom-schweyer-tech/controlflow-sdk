import io


def test_upload_creates_source_with_inferred_columns(client):
    csv = b"user_id,can_create,can_approve\nU1,true,false\n"
    resp = client.post(
        "/sources",
        data={"source_id": "users", "format": "csv"},
        files={"file": ("users.csv", io.BytesIO(csv), "text/csv")},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    edit = client.get("/sources/users")
    assert edit.status_code == 200
    for col in ("user_id", "can_create", "can_approve"):
        assert col in edit.text


def test_save_column_mapping(client):
    csv = b"user_id,amount\nU1,5\n"
    client.post("/sources", data={"source_id": "tx", "format": "csv"},
                files={"file": ("tx.csv", io.BytesIO(csv), "text/csv")},
                follow_redirects=False)
    resp = client.post("/sources/tx", data={
        "key_columns": "user_id",
        "display_name__user_id": "User ID", "data_type__user_id": "text",
        "is_key__user_id": "on", "include__user_id": "on",
        "display_name__amount": "Amount", "data_type__amount": "number",
        "include__amount": "on",
    }, follow_redirects=False)
    assert resp.status_code in (302, 303)
    # persisted
    from controlflow_sdk.store import repo
    from controlflow_sdk.store.db import connect
    conn = connect(client.app.state.project_root)
    src = repo.get_source(conn, "tx")
    conn.close()
    assert src["key_config"] == {"mode": "single", "columns": ["user_id"]}
    amount = next(c for c in src["columns"] if c["original_name"] == "amount")
    assert amount["data_type"] == "number" and amount["display_name"] == "Amount"


def test_save_source_metadata_persists(client):
    csv = b"invoice_id,amount\nINV1,5\n"
    client.post("/sources", data={"source_id": "invoices", "format": "csv"},
                files={"file": ("invoices.csv", io.BytesIO(csv), "text/csv")},
                follow_redirects=False)
    resp = client.post("/sources/invoices", data={
        "title": "Vendor Invoice Register",
        "description": "AP invoice extract for the period.",
        "extract_date": "2026-03-31",
        "key_columns": "invoice_id",
        "display_name__invoice_id": "Invoice ID", "data_type__invoice_id": "text",
        "is_key__invoice_id": "on", "include__invoice_id": "on",
        "display_name__amount": "Amount", "data_type__amount": "number",
        "include__amount": "on",
    }, follow_redirects=False)
    assert resp.status_code in (302, 303)

    from controlflow_sdk.store import repo
    from controlflow_sdk.store.db import connect
    conn = connect(client.app.state.project_root)
    src = repo.get_source(conn, "invoices")
    conn.close()
    assert src["title"] == "Vendor Invoice Register"
    assert src["description"] == "AP invoice extract for the period."
    assert src["extract_date"] == "2026-03-31"

    # The list shows the friendly title; the edit page round-trips the fields.
    assert "Vendor Invoice Register" in client.get("/sources").text
    edit = client.get("/sources/invoices").text
    assert "Vendor Invoice Register" in edit and "2026-03-31" in edit


def _upload(client, sid, csv):
    client.post("/sources", data={"source_id": sid, "format": "csv"},
                files={"file": (f"{sid}.csv", io.BytesIO(csv), "text/csv")},
                follow_redirects=False)


def test_add_source_page_renders(client):
    page = client.get("/sources/new")
    assert page.status_code == 200
    assert 'name="file"' in page.text and 'action="/sources"' in page.text


def test_sources_list_has_add_button_not_inline_form(client):
    page = client.get("/sources").text
    assert "/sources/new" in page
    # the upload form now lives on its own page, not the list
    assert 'enctype="multipart/form-data"' not in page


def test_refresh_same_columns_archives_and_preserves_mapping(client):
    _upload(client, "tx", b"user_id,amount\nU1,5\n")
    client.post("/sources/tx", data={
        "key_columns": "user_id",
        "display_name__user_id": "User ID", "data_type__user_id": "text",
        "is_key__user_id": "on", "include__user_id": "on",
        "display_name__amount": "Amount $", "data_type__amount": "number",
        "include__amount": "on",
    }, follow_redirects=False)

    new = b"user_id,amount\nU1,5\nU2,9\n"
    preview = client.post("/sources/tx/refresh",
                          files={"file": ("tx.csv", io.BytesIO(new), "text/csv")},
                          follow_redirects=False)
    assert preview.status_code == 200
    assert "/sources/tx/refresh/confirm" in preview.text
    assert "No column changes" in preview.text

    resp = client.post("/sources/tx/refresh/confirm",
                       data={"pending": "tx.csv"}, follow_redirects=False)
    assert resp.status_code in (302, 303)

    from controlflow_sdk.store import repo
    from controlflow_sdk.store.db import connect
    root = client.app.state.project_root
    conn = connect(root)
    src = repo.get_source(conn, "tx")
    conn.close()
    amount = next(c for c in src["columns"] if c["original_name"] == "amount")
    assert amount["display_name"] == "Amount $"  # mapping preserved
    assert (root / "data" / "tx.csv").read_bytes() == new  # data replaced
    versions = list((root / "data" / ".versions" / "tx").glob("*"))
    assert len(versions) == 1  # old file archived, not lost
    assert "Previous versions" in client.get("/sources/tx").text


def test_refresh_diff_columns_reconciles_after_confirm(client):
    _upload(client, "acc", b"acct_id,balance\n1,2\n")
    client.post("/sources/acc", data={
        "display_name__acct_id": "Account", "data_type__acct_id": "text",
        "include__acct_id": "on",
        "display_name__balance": "Balance", "data_type__balance": "number",
        "include__balance": "on",
    }, follow_redirects=False)

    new = b"acct_id,status\n1,active\n"
    preview = client.post("/sources/acc/refresh",
                          files={"file": ("acc.csv", io.BytesIO(new), "text/csv")},
                          follow_redirects=False)
    assert preview.status_code == 200
    assert "Added" in preview.text and "status" in preview.text  # added column surfaced
    assert "Removed" in preview.text and "balance" in preview.text  # removed column surfaced

    client.post("/sources/acc/refresh/confirm",
                data={"pending": "acc.csv"}, follow_redirects=False)

    from controlflow_sdk.store import repo
    from controlflow_sdk.store.db import connect
    conn = connect(client.app.state.project_root)
    src = repo.get_source(conn, "acc")
    conn.close()
    cols = {c["original_name"]: c for c in src["columns"]}
    assert list(cols) == ["acct_id", "status"]  # balance dropped, status added, new-file order
    assert cols["acct_id"]["display_name"] == "Account"  # surviving mapping preserved
    assert cols["status"]["display_name"] == "status"  # new column gets defaults


def test_refresh_cancel_discards_pending_and_keeps_current(client):
    _upload(client, "keep", b"a\n1\n")
    original = (client.app.state.project_root / "data" / "keep.csv").read_bytes()
    client.post("/sources/keep/refresh",
                files={"file": ("keep.csv", io.BytesIO(b"a\n2\n"), "text/csv")},
                follow_redirects=False)
    resp = client.post("/sources/keep/refresh/cancel",
                       data={"pending": "keep.csv"}, follow_redirects=False)
    assert resp.status_code in (302, 303)
    root = client.app.state.project_root
    assert (root / "data" / "keep.csv").read_bytes() == original  # untouched
    assert not list((root / "data" / ".versions" / "keep").glob("*")) if (
        root / "data" / ".versions" / "keep").is_dir() else True  # nothing archived


def test_blank_title_clears_to_none(client):
    csv = b"a\n1\n"
    client.post("/sources", data={"source_id": "s", "format": "csv"},
                files={"file": ("s.csv", io.BytesIO(csv), "text/csv")},
                follow_redirects=False)
    client.post("/sources/s", data={"title": "   ", "display_name__a": "A",
                                     "data_type__a": "text", "include__a": "on"},
                follow_redirects=False)
    from controlflow_sdk.store import repo
    from controlflow_sdk.store.db import connect
    conn = connect(client.app.state.project_root)
    assert repo.get_source(conn, "s")["title"] is None
    conn.close()
