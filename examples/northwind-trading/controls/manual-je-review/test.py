"""Manual journal entry review — segregation of duties.

Flags manual journal entries >= $50,000 where the reviewer is either absent
or is the same person as the preparer.
"""

import pandas as pd


def test(pop):  # noqa: ANN001, ANN201
    df = pop.df
    violations = []

    for _, row in df.iterrows():
        # Only care about manual entries
        if str(row.get("entry_type", "")).strip().lower() != "manual":
            continue

        # Coerce amount safely
        try:
            amount = float(row["amount"])
        except (ValueError, TypeError):
            continue

        if abs(amount) < 50000:  # materiality on absolute value (large credits count too)
            continue

        prepared_by = str(row.get("prepared_by", "") or "").strip()
        reviewed_by = str(row.get("reviewed_by", "") or "").strip()

        # Check for missing reviewer (NaN or empty string)
        reviewer_missing = pd.isna(row.get("reviewed_by")) or reviewed_by == ""
        # Check for self-review
        self_reviewed = not reviewer_missing and reviewed_by == prepared_by

        if reviewer_missing or self_reviewed:
            reason = (
                "No independent reviewer assigned"
                if reviewer_missing
                else "Entry reviewed by preparer (self-authorization)"
            )
            violations.append(
                {
                    "item_key": str(row["entry_id"]),
                    "description": reason,
                    "severity": "high",
                    "details": {
                        "amount": amount,
                        "prepared_by": prepared_by,
                    },
                }
            )

    return violations
