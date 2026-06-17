"""Accounts payable three-way match.

For each payment:
  1. Look up the invoice by invoice_id — flag if missing.
  2. Look up the PO by po_id from the invoice — flag if PO missing.
  3. Flag if PO status != 'approved'.
  4. Flag if abs(payment.amount - po.amount) / po.amount > 0.01.
"""


def test(pop, sources):  # noqa: ANN001, ANN201
    payments_df = pop.df
    invoices_df = sources["invoices"].df
    po_df = sources["purchase_orders"].df

    # Index by key columns for O(1) lookup. drop_duplicates guards against a
    # repeated id (e.g. a credit note reusing an invoice_id) so each .loc lookup
    # returns a single row, not a DataFrame.
    invoices = invoices_df.drop_duplicates(subset="invoice_id", keep="first").set_index(
        "invoice_id"
    )
    pos = po_df.drop_duplicates(subset="po_id", keep="first").set_index("po_id")

    violations = []

    for _, pmt in payments_df.iterrows():
        payment_id = str(pmt["payment_id"])
        invoice_id = str(pmt.get("invoice_id", "") or "").strip()

        try:
            pmt_amount = float(pmt["amount"])
        except (ValueError, TypeError):
            pmt_amount = 0.0

        # ── Check 1: invoice must exist ──────────────────────────────────────
        if invoice_id not in invoices.index:
            violations.append(
                {
                    "item_key": payment_id,
                    "description": (
                        f"Payment references invoice '{invoice_id}' "
                        "which does not exist in the invoice register"
                    ),
                    "severity": "high",
                    "details": {"invoice_id": invoice_id, "reason": "missing_invoice"},
                }
            )
            continue

        inv_row = invoices.loc[invoice_id]
        po_id = str(inv_row.get("po_id", "") or "").strip()

        # ── Check 2: PO must exist ───────────────────────────────────────────
        if po_id not in pos.index:
            violations.append(
                {
                    "item_key": payment_id,
                    "description": (
                        f"Invoice '{invoice_id}' references PO '{po_id}' "
                        "which does not exist in the purchase order register"
                    ),
                    "severity": "high",
                    "details": {
                        "invoice_id": invoice_id,
                        "po_id": po_id,
                        "reason": "missing_po",
                    },
                }
            )
            continue

        po_row = pos.loc[po_id]

        # ── Check 3: PO must be approved ─────────────────────────────────────
        po_status = str(po_row.get("status", "") or "").strip().lower()
        if po_status != "approved":
            violations.append(
                {
                    "item_key": payment_id,
                    "description": (
                        f"PO '{po_id}' linked to invoice '{invoice_id}' "
                        f"has status '{po_status}' (expected 'approved')"
                    ),
                    "severity": "high",
                    "details": {
                        "invoice_id": invoice_id,
                        "po_id": po_id,
                        "po_status": po_status,
                        "reason": "unapproved_po",
                    },
                }
            )
            continue

        # ── Check 4: amount within 1% of PO amount ───────────────────────────
        try:
            po_amount = float(po_row["amount"])
        except (ValueError, TypeError):
            po_amount = 0.0

        if po_amount > 0 and abs(pmt_amount - po_amount) / po_amount > 0.01:
            violations.append(
                {
                    "item_key": payment_id,
                    "description": (
                        f"Payment amount {pmt_amount:,.2f} deviates from "
                        f"PO '{po_id}' amount {po_amount:,.2f} by more than 1%"
                    ),
                    "severity": "high",
                    "details": {
                        "invoice_id": invoice_id,
                        "po_id": po_id,
                        "payment_amount": pmt_amount,
                        "po_amount": po_amount,
                        "reason": "amount_variance",
                    },
                }
            )

    return violations
