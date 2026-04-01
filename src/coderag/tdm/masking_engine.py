"""Masking policy helpers for TDM catalog workflows."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable


def apply_masking_value(
    value: Any,
    policy_type: str,
    seed: str = "tdm",
) -> Any:
    """Apply deterministic masking policy to one scalar value."""
    if value is None:
        return None

    text_value = str(value)
    normalized_policy = policy_type.strip().lower()

    if normalized_policy in {"mask", "redact"}:
        return "*" * max(4, min(len(text_value), 12))

    if normalized_policy == "hash":
        digest = hashlib.sha256(f"{seed}:{text_value}".encode("utf-8"))
        return digest.hexdigest()[:16]

    if normalized_policy == "tokenize":
        digest = hashlib.sha1(f"{seed}:{text_value}".encode("utf-8"))
        return f"tok_{digest.hexdigest()[:12]}"

    if normalized_policy in {"preserve-last4", "last4"}:
        if len(text_value) <= 4:
            return text_value
        return "*" * (len(text_value) - 4) + text_value[-4:]

    return text_value


def apply_masking_rules_to_row(
    row: Dict[str, Any],
    rules: Iterable[Dict[str, Any]],
    seed: str = "tdm",
) -> Dict[str, Any]:
    """Apply column-scoped masking rules to one row dictionary."""
    masked_row = dict(row)
    for rule in rules:
        column_name = str(rule.get("column_name") or "").strip()
        if not column_name:
            continue
        if column_name not in masked_row:
            continue
        policy_type = str(rule.get("policy_type") or "mask")
        masked_row[column_name] = apply_masking_value(
            masked_row[column_name],
            policy_type=policy_type,
            seed=seed,
        )
    return masked_row
