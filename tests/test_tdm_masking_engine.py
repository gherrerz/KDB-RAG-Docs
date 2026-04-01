"""Tests for TDM masking policy helpers."""

from __future__ import annotations

from coderag.tdm.masking_engine import apply_masking_rules_to_row, apply_masking_value


def test_apply_masking_value_tokenize_is_deterministic() -> None:
    """Return deterministic tokens for equal input and seed."""
    left = apply_masking_value("john@example.com", policy_type="tokenize", seed="x")
    right = apply_masking_value("john@example.com", policy_type="tokenize", seed="x")
    assert left == right
    assert str(left).startswith("tok_")


def test_apply_masking_value_hash_changes_with_seed() -> None:
    """Generate different hashes when seed changes."""
    left = apply_masking_value("12345", policy_type="hash", seed="a")
    right = apply_masking_value("12345", policy_type="hash", seed="b")
    assert left != right


def test_apply_masking_rules_to_row_applies_column_rules() -> None:
    """Mask only columns present in rule list."""
    row = {"customer_email": "john@example.com", "amount": "100.00"}
    rules = [
        {"column_name": "customer_email", "policy_type": "tokenize"},
    ]
    masked = apply_masking_rules_to_row(row=row, rules=rules, seed="seed")

    assert masked["customer_email"] != row["customer_email"]
    assert masked["amount"] == row["amount"]
