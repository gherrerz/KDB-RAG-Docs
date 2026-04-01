"""TDM ingestion orchestration for schema/service/masking metadata."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List

from coderag.core.models import SourceConfig
from coderag.storage.metadata_store import MetadataStore
from coderag.parsers.data_dictionary_parser import parse_data_dictionary
from coderag.parsers.openapi_service_parser import parse_openapi_service_contract
from coderag.parsers.sql_schema_parser import parse_sql_schema

TDM_ALLOWED_EXTENSIONS = {".sql", ".json", ".yaml", ".yml", ".md", ".txt"}


def _source_id_from_path(path: str) -> str:
    """Build deterministic source id from one filesystem path."""
    digest = hashlib.sha1(path.encode("utf-8")).hexdigest()
    return digest[:12]


def _stable_id(*parts: str) -> str:
    """Build deterministic short IDs for TDM entities."""
    raw = "::".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _discover_tdm_files(root: Path) -> List[Path]:
    """Return candidate TDM files from one root directory."""
    discovered: List[Path] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in TDM_ALLOWED_EXTENSIONS:
            continue
        discovered.append(file_path)
    return discovered


def _read_text(file_path: Path) -> str:
    """Read UTF-8 text while preserving ingestion resilience."""
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return file_path.read_text(encoding="latin-1")


def ingest_tdm_assets(
    source: SourceConfig,
    store: MetadataStore,
) -> Dict[str, Any]:
    """Ingest TDM-specific metadata into additive SQLite tables."""
    if source.source_type not in {"tdm_folder", "tdm"}:
        raise ValueError(
            "TDM ingestion expects source_type 'tdm_folder' or 'tdm'."
        )
    if not source.local_path:
        raise ValueError("TDM ingestion requires source.local_path.")

    root = Path(source.local_path).expanduser().resolve(strict=False)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"TDM source path is invalid: {root}")

    source_id = _source_id_from_path(str(root))
    discovered_files = _discover_tdm_files(root)

    created_default_schema = False
    default_schema_id = _stable_id(source_id, "schema", "public")

    summary = {
        "source_id": source_id,
        "source_path": str(root),
        "discovered_files": len(discovered_files),
        "schemas": 0,
        "tables": 0,
        "columns": 0,
        "service_mappings": 0,
        "masking_rules": 0,
    }

    schema_ids_by_name: Dict[str, str] = {}
    table_ids_by_key: Dict[str, str] = {}
    column_ids_by_key: Dict[str, str] = {}

    for file_path in discovered_files:
        text = _read_text(file_path)
        suffix = file_path.suffix.lower()

        if suffix == ".sql":
            sql_assets = parse_sql_schema(text)
            for schema in sql_assets.get("schemas", []):
                schema_name = str(schema.get("schema_name", "public"))
                schema_id = _stable_id(source_id, "schema", schema_name)
                schema_ids_by_name[schema_name] = schema_id
                store.upsert_tdm_schema(
                    schema_id=schema_id,
                    source_id=source_id,
                    database_name=str(schema.get("database_name", "default")),
                    schema_name=schema_name,
                    metadata={"origin": "sql", "path": str(file_path)},
                )
                summary["schemas"] += 1

            for table in sql_assets.get("tables", []):
                schema_name = str(table.get("schema_name", "public"))
                schema_id = schema_ids_by_name.get(schema_name)
                if schema_id is None:
                    schema_id = _stable_id(source_id, "schema", schema_name)
                    schema_ids_by_name[schema_name] = schema_id
                table_name = str(table.get("table_name", "unknown_table"))
                table_key = f"{schema_name}.{table_name}"
                table_id = _stable_id(source_id, "table", table_key)
                table_ids_by_key[table_key] = table_id
                store.upsert_tdm_table(
                    table_id=table_id,
                    source_id=source_id,
                    schema_id=schema_id,
                    table_name=table_name,
                    table_type=str(table.get("table_type", "table")),
                    metadata={
                        "origin": "sql",
                        "schema_name": schema_name,
                        "path": str(file_path),
                    },
                )
                summary["tables"] += 1

            for column in sql_assets.get("columns", []):
                schema_name = str(column.get("schema_name", "public"))
                table_name = str(column.get("table_name", "unknown_table"))
                column_name = str(column.get("column_name", "unknown_column"))
                table_key = f"{schema_name}.{table_name}"
                table_id = table_ids_by_key.get(table_key)
                if table_id is None:
                    table_id = _stable_id(source_id, "table", table_key)
                    table_ids_by_key[table_key] = table_id
                column_key = f"{table_key}.{column_name}"
                column_id = _stable_id(source_id, "column", column_key)
                column_ids_by_key[column_key] = column_id
                store.upsert_tdm_column(
                    column_id=column_id,
                    source_id=source_id,
                    table_id=table_id,
                    column_name=column_name,
                    data_type=str(column.get("data_type", "text")),
                    nullable=bool(column.get("nullable", True)),
                    pii_class=column.get("pii_class"),
                    metadata={
                        "origin": "sql",
                        "schema_name": schema_name,
                        "table_name": table_name,
                        "path": str(file_path),
                    },
                )
                summary["columns"] += 1
            continue

        if suffix in {".json", ".yaml", ".yml"}:
            openapi_assets = parse_openapi_service_contract(
                text=text,
                path_hint=str(file_path),
            )
            service_name = str(
                openapi_assets.get("service_name", "unknown-service")
            )
            mappings = openapi_assets.get("mappings", [])
            if not isinstance(mappings, list):
                mappings = []
            for item in mappings:
                endpoint = str(item.get("endpoint", ""))
                method = str(item.get("method", "GET"))
                if not endpoint:
                    continue

                table_name = item.get("table_name")
                if table_name:
                    table_key = str(table_name)
                    if "." not in table_key:
                        table_key = f"public.{table_key}"
                else:
                    table_key = "public.__unmapped__"

                table_id = table_ids_by_key.get(table_key)
                if table_id is None:
                    if not created_default_schema:
                        store.upsert_tdm_schema(
                            schema_id=default_schema_id,
                            source_id=source_id,
                            database_name="default",
                            schema_name="public",
                            metadata={"origin": "tdm_openapi_fallback"},
                        )
                        created_default_schema = True
                    table_id = _stable_id(source_id, "table", table_key)
                    table_ids_by_key[table_key] = table_id
                    store.upsert_tdm_table(
                        table_id=table_id,
                        source_id=source_id,
                        schema_id=default_schema_id,
                        table_name=table_key.split(".", 1)[1],
                        table_type="virtual",
                        metadata={"origin": "openapi", "path": str(file_path)},
                    )
                    summary["tables"] += 1

                mapping_id = _stable_id(
                    source_id,
                    "mapping",
                    service_name,
                    method,
                    endpoint,
                )
                store.upsert_tdm_service_mapping(
                    mapping_id=mapping_id,
                    source_id=source_id,
                    service_name=service_name,
                    endpoint=endpoint,
                    method=method,
                    table_id=table_id,
                    metadata={
                        "origin": "openapi",
                        "operation_id": item.get("operation_id", ""),
                        "path": str(file_path),
                    },
                )
                summary["service_mappings"] += 1
            continue

        if suffix in {".md", ".txt"}:
            dictionary_assets = parse_data_dictionary(text)
            rules = dictionary_assets.get("masking_rules", [])
            if not isinstance(rules, list):
                rules = []
            for rule in rules:
                table_name = rule.get("table_name")
                table_id = None
                if isinstance(table_name, str) and table_name:
                    table_key = table_name
                    if "." not in table_key:
                        table_key = f"public.{table_key}"
                    table_id = table_ids_by_key.get(table_key)

                column_id = None
                column_name = rule.get("column_name")
                if table_id and isinstance(column_name, str) and column_name:
                    for known_key, known_column_id in column_ids_by_key.items():
                        if known_key.endswith(f".{column_name}"):
                            column_id = known_column_id
                            break

                rule_name = str(rule.get("rule_name", "mask-rule"))
                rule_id = _stable_id(source_id, "masking", rule_name, str(file_path))
                metadata = dict(rule.get("metadata", {}))
                metadata["path"] = str(file_path)
                store.upsert_tdm_masking_rule(
                    rule_id=rule_id,
                    source_id=source_id,
                    rule_name=rule_name,
                    policy_type=str(rule.get("policy_type", "mask")),
                    scope=str(rule.get("scope", "global")),
                    table_id=table_id,
                    column_id=column_id,
                    priority=int(rule.get("priority", 100)),
                    metadata=metadata,
                )
                summary["masking_rules"] += 1

    return summary
