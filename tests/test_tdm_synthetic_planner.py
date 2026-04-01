"""Tests for synthetic profile planner."""

from __future__ import annotations

from coderag.tdm.synthetic_planner import build_synthetic_profile_plan


def test_build_synthetic_profile_plan_assigns_generators() -> None:
    """Choose generator strategy based on pii class and data type hints."""
    plan = build_synthetic_profile_plan(
        table_name="invoices",
        columns=[
            {"column_name": "customer_email", "data_type": "varchar", "pii_class": "email"},
            {"column_name": "total_amount", "data_type": "decimal(10,2)", "pii_class": None},
            {"column_name": "notes", "data_type": "text", "pii_class": None},
        ],
        target_rows=250,
    )

    assert plan["table_name"] == "invoices"
    assert plan["target_rows"] == 250
    assert len(plan["columns"]) == 3
    by_name = {item["column_name"]: item for item in plan["columns"]}
    assert by_name["customer_email"]["generator"] == "synthetic_email"
    assert by_name["total_amount"]["generator"] == "numeric_distribution"
    assert by_name["notes"]["generator"] == "random_text"
