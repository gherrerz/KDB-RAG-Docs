"""Extract TDM hints from data dictionary and governance text files."""

from __future__ import annotations

import re
from typing import Any, Dict, List

COLUMN_HINT_PATTERN = re.compile(
    r"\b(?:column|columna)\s*[:\-]?\s*(?P<name>[\w\.\-]+)",
    re.IGNORECASE,
)
PII_HINT_PATTERN = re.compile(
    r"\b(email|telefono|phone|dni|ssn|passport|iban|card|tarjeta)\b",
    re.IGNORECASE,
)
MASKING_HINT_PATTERN = re.compile(
    r"\b(mask|masking|enmascar|tokeniz|hash)\w*\b",
    re.IGNORECASE,
)
TABLE_CONTEXT_PATTERN = re.compile(
    r"\b(?:table|tabla)\s*[:\-]?\s*(?P<table>[\w\.\-]+)",
    re.IGNORECASE,
)


def parse_data_dictionary(text: str) -> Dict[str, Any]:
    """Extract masking and sensitivity hints from plain governance text."""
    rules: List[Dict[str, Any]] = []
    table_name = None

    table_match = TABLE_CONTEXT_PATTERN.search(text)
    if table_match:
        table_name = table_match.group("table").strip()

    columns = [
        match.group("name").strip()
        for match in COLUMN_HINT_PATTERN.finditer(text)
    ]
    pii_hints = [match.group(1).lower() for match in PII_HINT_PATTERN.finditer(text)]

    if columns and pii_hints:
        for idx, column_name in enumerate(columns):
            pii_class = pii_hints[min(idx, len(pii_hints) - 1)]
            rules.append(
                {
                    "rule_name": f"mask-{column_name}",
                    "policy_type": "tokenize",
                    "scope": "column",
                    "table_name": table_name,
                    "column_name": column_name,
                    "priority": 100,
                    "metadata": {
                        "pii_class": pii_class,
                        "source": "data_dictionary",
                    },
                }
            )

    if not rules and MASKING_HINT_PATTERN.search(text):
        rules.append(
            {
                "rule_name": "mask-generic-policy",
                "policy_type": "mask",
                "scope": "table" if table_name else "global",
                "table_name": table_name,
                "column_name": None,
                "priority": 200,
                "metadata": {"source": "data_dictionary"},
            }
        )

    return {"masking_rules": rules}
