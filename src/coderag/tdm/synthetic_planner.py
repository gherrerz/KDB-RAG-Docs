"""Synthetic data planning utilities for TDM enablement."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


def build_synthetic_profile_plan(
    table_name: str,
    columns: Iterable[Dict[str, Any]],
    target_rows: int = 1000,
) -> Dict[str, Any]:
    """Build a deterministic synthetic profile plan from table metadata."""
    column_plans: List[Dict[str, Any]] = []
    for column in columns:
        column_name = str(column.get("column_name") or "")
        data_type = str(column.get("data_type") or "text")
        pii_class = column.get("pii_class")

        generator = "random_text"
        if pii_class == "email":
            generator = "synthetic_email"
        elif pii_class in {"phone", "telefono"}:
            generator = "synthetic_phone"
        elif "int" in data_type.casefold() or "decimal" in data_type.casefold():
            generator = "numeric_distribution"

        column_plans.append(
            {
                "column_name": column_name,
                "data_type": data_type,
                "pii_class": pii_class,
                "generator": generator,
            }
        )

    return {
        "table_name": table_name,
        "target_rows": max(1, int(target_rows)),
        "columns": column_plans,
        "strategy": "template",
    }
