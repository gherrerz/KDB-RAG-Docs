# pyright: reportMissingImports=false

"""PostgreSQL-backed TDM catalog storage for the Docs cutover."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from coderag.storage.postgres_schema import (
    tdm_columns_table,
    tdm_masking_rules_table,
    tdm_schemas_table,
    tdm_service_mappings_table,
    tdm_synthetic_profiles_table,
    tdm_tables_table,
    tdm_virtualization_artifacts_table,
)
from coderag.storage.postgres_session import PostgresSessionFactory


class PostgresTdmStore:
    """Persist TDM catalog entities in PostgreSQL."""

    def __init__(
        self,
        postgres_dsn: str,
        *,
        session_factory: PostgresSessionFactory | None = None,
    ) -> None:
        """Create the store using a reusable SQLAlchemy session factory."""
        self._session_factory = session_factory or PostgresSessionFactory(
            postgres_dsn
        )

    @staticmethod
    def _now() -> datetime:
        """Return a timezone-aware timestamp for writes."""
        return datetime.now(UTC)

    @staticmethod
    def _coerce_payload_dict(value: Any) -> dict[str, Any]:
        """Normalize JSON payloads to predictable dictionary values."""
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str) and value.strip():
            try:
                loaded = json.loads(value)
            except json.JSONDecodeError:
                return {}
            if isinstance(loaded, dict):
                return loaded
        return {}

    def upsert_tdm_schema(
        self,
        schema_id: str,
        source_id: str,
        database_name: str,
        schema_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or update one TDM schema asset."""
        now = self._now()
        insert_stmt = insert(tdm_schemas_table).values(
            schema_id=schema_id,
            source_id=source_id,
            database_name=database_name,
            schema_name=schema_name,
            metadata_json=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        statement = insert_stmt.on_conflict_do_update(
            index_elements=[tdm_schemas_table.c.schema_id],
            set_={
                "source_id": insert_stmt.excluded.source_id,
                "database_name": insert_stmt.excluded.database_name,
                "schema_name": insert_stmt.excluded.schema_name,
                "metadata_json": insert_stmt.excluded.metadata_json,
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)

    def list_tdm_schemas(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return stored TDM schema assets, optionally filtered by source."""
        statement = select(
            tdm_schemas_table.c.schema_id,
            tdm_schemas_table.c.source_id,
            tdm_schemas_table.c.database_name,
            tdm_schemas_table.c.schema_name,
            tdm_schemas_table.c.metadata_json,
        )
        if source_id:
            statement = statement.where(tdm_schemas_table.c.source_id == source_id)
        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            {
                "schema_id": str(row["schema_id"]),
                "source_id": str(row["source_id"]),
                "database_name": str(row["database_name"]),
                "schema_name": str(row["schema_name"]),
                "metadata": self._coerce_payload_dict(row["metadata_json"]),
            }
            for row in rows
        ]

    def upsert_tdm_table(
        self,
        table_id: str,
        source_id: str,
        schema_id: str,
        table_name: str,
        table_type: str = "table",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or update one TDM table asset."""
        now = self._now()
        insert_stmt = insert(tdm_tables_table).values(
            table_id=table_id,
            source_id=source_id,
            schema_id=schema_id,
            table_name=table_name,
            table_type=table_type,
            metadata_json=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        statement = insert_stmt.on_conflict_do_update(
            index_elements=[tdm_tables_table.c.table_id],
            set_={
                "source_id": insert_stmt.excluded.source_id,
                "schema_id": insert_stmt.excluded.schema_id,
                "table_name": insert_stmt.excluded.table_name,
                "table_type": insert_stmt.excluded.table_type,
                "metadata_json": insert_stmt.excluded.metadata_json,
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)

    def list_tdm_tables(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return stored TDM table assets, optionally filtered by source."""
        statement = select(
            tdm_tables_table.c.table_id,
            tdm_tables_table.c.source_id,
            tdm_tables_table.c.schema_id,
            tdm_tables_table.c.table_name,
            tdm_tables_table.c.table_type,
            tdm_tables_table.c.metadata_json,
        )
        if source_id:
            statement = statement.where(tdm_tables_table.c.source_id == source_id)
        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            {
                "table_id": str(row["table_id"]),
                "source_id": str(row["source_id"]),
                "schema_id": str(row["schema_id"]),
                "table_name": str(row["table_name"]),
                "table_type": str(row["table_type"]),
                "metadata": self._coerce_payload_dict(row["metadata_json"]),
            }
            for row in rows
        ]

    def upsert_tdm_column(
        self,
        column_id: str,
        source_id: str,
        table_id: str,
        column_name: str,
        data_type: str,
        nullable: bool = True,
        pii_class: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or update one TDM column asset."""
        now = self._now()
        insert_stmt = insert(tdm_columns_table).values(
            column_id=column_id,
            source_id=source_id,
            table_id=table_id,
            column_name=column_name,
            data_type=data_type,
            nullable=bool(nullable),
            pii_class=pii_class,
            metadata_json=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        statement = insert_stmt.on_conflict_do_update(
            index_elements=[tdm_columns_table.c.column_id],
            set_={
                "source_id": insert_stmt.excluded.source_id,
                "table_id": insert_stmt.excluded.table_id,
                "column_name": insert_stmt.excluded.column_name,
                "data_type": insert_stmt.excluded.data_type,
                "nullable": insert_stmt.excluded.nullable,
                "pii_class": insert_stmt.excluded.pii_class,
                "metadata_json": insert_stmt.excluded.metadata_json,
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)

    def list_tdm_columns(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return stored TDM column assets, optionally filtered by source."""
        statement = select(
            tdm_columns_table.c.column_id,
            tdm_columns_table.c.source_id,
            tdm_columns_table.c.table_id,
            tdm_columns_table.c.column_name,
            tdm_columns_table.c.data_type,
            tdm_columns_table.c.nullable,
            tdm_columns_table.c.pii_class,
            tdm_columns_table.c.metadata_json,
        )
        if source_id:
            statement = statement.where(tdm_columns_table.c.source_id == source_id)
        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            {
                "column_id": str(row["column_id"]),
                "source_id": str(row["source_id"]),
                "table_id": str(row["table_id"]),
                "column_name": str(row["column_name"]),
                "data_type": str(row["data_type"]),
                "nullable": bool(row["nullable"]),
                "pii_class": (
                    str(row["pii_class"])
                    if row["pii_class"] is not None
                    else None
                ),
                "metadata": self._coerce_payload_dict(row["metadata_json"]),
            }
            for row in rows
        ]

    def upsert_tdm_service_mapping(
        self,
        mapping_id: str,
        source_id: str,
        service_name: str,
        endpoint: str,
        method: str,
        table_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or update one service-to-table mapping for TDM."""
        now = self._now()
        insert_stmt = insert(tdm_service_mappings_table).values(
            mapping_id=mapping_id,
            source_id=source_id,
            service_name=service_name,
            endpoint=endpoint,
            method=method,
            table_id=table_id,
            metadata_json=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        statement = insert_stmt.on_conflict_do_update(
            index_elements=[tdm_service_mappings_table.c.mapping_id],
            set_={
                "source_id": insert_stmt.excluded.source_id,
                "service_name": insert_stmt.excluded.service_name,
                "endpoint": insert_stmt.excluded.endpoint,
                "method": insert_stmt.excluded.method,
                "table_id": insert_stmt.excluded.table_id,
                "metadata_json": insert_stmt.excluded.metadata_json,
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)

    def list_tdm_service_mappings(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return stored service mappings, optionally filtered by source."""
        statement = select(
            tdm_service_mappings_table.c.mapping_id,
            tdm_service_mappings_table.c.source_id,
            tdm_service_mappings_table.c.service_name,
            tdm_service_mappings_table.c.endpoint,
            tdm_service_mappings_table.c.method,
            tdm_service_mappings_table.c.table_id,
            tdm_service_mappings_table.c.metadata_json,
        )
        if source_id:
            statement = statement.where(
                tdm_service_mappings_table.c.source_id == source_id
            )
        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            {
                "mapping_id": str(row["mapping_id"]),
                "source_id": str(row["source_id"]),
                "service_name": str(row["service_name"]),
                "endpoint": str(row["endpoint"]),
                "method": str(row["method"]),
                "table_id": str(row["table_id"]),
                "metadata": self._coerce_payload_dict(row["metadata_json"]),
            }
            for row in rows
        ]

    def upsert_tdm_masking_rule(
        self,
        rule_id: str,
        source_id: str,
        rule_name: str,
        policy_type: str,
        scope: str,
        table_id: str | None = None,
        column_id: str | None = None,
        priority: int = 100,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or update one TDM masking rule."""
        now = self._now()
        insert_stmt = insert(tdm_masking_rules_table).values(
            rule_id=rule_id,
            source_id=source_id,
            rule_name=rule_name,
            policy_type=policy_type,
            scope=scope,
            table_id=table_id,
            column_id=column_id,
            priority=int(priority),
            metadata_json=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        statement = insert_stmt.on_conflict_do_update(
            index_elements=[tdm_masking_rules_table.c.rule_id],
            set_={
                "source_id": insert_stmt.excluded.source_id,
                "rule_name": insert_stmt.excluded.rule_name,
                "policy_type": insert_stmt.excluded.policy_type,
                "scope": insert_stmt.excluded.scope,
                "table_id": insert_stmt.excluded.table_id,
                "column_id": insert_stmt.excluded.column_id,
                "priority": insert_stmt.excluded.priority,
                "metadata_json": insert_stmt.excluded.metadata_json,
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)

    def list_tdm_masking_rules(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return stored masking rules, optionally filtered by source."""
        statement = select(
            tdm_masking_rules_table.c.rule_id,
            tdm_masking_rules_table.c.source_id,
            tdm_masking_rules_table.c.rule_name,
            tdm_masking_rules_table.c.policy_type,
            tdm_masking_rules_table.c.scope,
            tdm_masking_rules_table.c.table_id,
            tdm_masking_rules_table.c.column_id,
            tdm_masking_rules_table.c.priority,
            tdm_masking_rules_table.c.metadata_json,
        )
        if source_id:
            statement = statement.where(
                tdm_masking_rules_table.c.source_id == source_id
            )
        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            {
                "rule_id": str(row["rule_id"]),
                "source_id": str(row["source_id"]),
                "rule_name": str(row["rule_name"]),
                "policy_type": str(row["policy_type"]),
                "scope": str(row["scope"]),
                "table_id": (
                    str(row["table_id"])
                    if row["table_id"] is not None
                    else None
                ),
                "column_id": (
                    str(row["column_id"])
                    if row["column_id"] is not None
                    else None
                ),
                "priority": int(row["priority"]),
                "metadata": self._coerce_payload_dict(row["metadata_json"]),
            }
            for row in rows
        ]

    def upsert_tdm_virtualization_artifact(
        self,
        artifact_id: str,
        source_id: str,
        service_name: str,
        artifact_type: str,
        content: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or update one virtualization artifact for TDM."""
        now = self._now()
        insert_stmt = insert(tdm_virtualization_artifacts_table).values(
            artifact_id=artifact_id,
            source_id=source_id,
            service_name=service_name,
            artifact_type=artifact_type,
            content_json=dict(content or {}),
            metadata_json=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        statement = insert_stmt.on_conflict_do_update(
            index_elements=[tdm_virtualization_artifacts_table.c.artifact_id],
            set_={
                "source_id": insert_stmt.excluded.source_id,
                "service_name": insert_stmt.excluded.service_name,
                "artifact_type": insert_stmt.excluded.artifact_type,
                "content_json": insert_stmt.excluded.content_json,
                "metadata_json": insert_stmt.excluded.metadata_json,
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)

    def list_tdm_virtualization_artifacts(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return virtualization artifacts, optionally filtered by source."""
        statement = select(
            tdm_virtualization_artifacts_table.c.artifact_id,
            tdm_virtualization_artifacts_table.c.source_id,
            tdm_virtualization_artifacts_table.c.service_name,
            tdm_virtualization_artifacts_table.c.artifact_type,
            tdm_virtualization_artifacts_table.c.content_json,
            tdm_virtualization_artifacts_table.c.metadata_json,
        )
        if source_id:
            statement = statement.where(
                tdm_virtualization_artifacts_table.c.source_id == source_id
            )
        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            {
                "artifact_id": str(row["artifact_id"]),
                "source_id": str(row["source_id"]),
                "service_name": str(row["service_name"]),
                "artifact_type": str(row["artifact_type"]),
                "content": self._coerce_payload_dict(row["content_json"]),
                "metadata": self._coerce_payload_dict(row["metadata_json"]),
            }
            for row in rows
        ]

    def upsert_tdm_synthetic_profile(
        self,
        profile_id: str,
        source_id: str,
        profile_name: str,
        strategy: str = "template",
        target_table_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or update one synthetic data profile for TDM."""
        now = self._now()
        insert_stmt = insert(tdm_synthetic_profiles_table).values(
            profile_id=profile_id,
            source_id=source_id,
            profile_name=profile_name,
            target_table_id=target_table_id,
            strategy=strategy,
            metadata_json=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        statement = insert_stmt.on_conflict_do_update(
            index_elements=[tdm_synthetic_profiles_table.c.profile_id],
            set_={
                "source_id": insert_stmt.excluded.source_id,
                "profile_name": insert_stmt.excluded.profile_name,
                "target_table_id": insert_stmt.excluded.target_table_id,
                "strategy": insert_stmt.excluded.strategy,
                "metadata_json": insert_stmt.excluded.metadata_json,
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)

    def list_tdm_synthetic_profiles(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return synthetic profiles, optionally filtered by source."""
        statement = select(
            tdm_synthetic_profiles_table.c.profile_id,
            tdm_synthetic_profiles_table.c.source_id,
            tdm_synthetic_profiles_table.c.profile_name,
            tdm_synthetic_profiles_table.c.target_table_id,
            tdm_synthetic_profiles_table.c.strategy,
            tdm_synthetic_profiles_table.c.metadata_json,
        )
        if source_id:
            statement = statement.where(
                tdm_synthetic_profiles_table.c.source_id == source_id
            )
        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            {
                "profile_id": str(row["profile_id"]),
                "source_id": str(row["source_id"]),
                "profile_name": str(row["profile_name"]),
                "target_table_id": (
                    str(row["target_table_id"])
                    if row["target_table_id"] is not None
                    else None
                ),
                "strategy": str(row["strategy"]),
                "metadata": self._coerce_payload_dict(row["metadata_json"]),
            }
            for row in rows
        ]

    def clear_tdm_data(self) -> dict[str, int]:
        """Delete persisted TDM rows so reset remains behaviorally coherent."""
        with self._session_factory.get_connection() as connection:
            deleted_virtualization = connection.execute(
                delete(tdm_virtualization_artifacts_table)
            ).rowcount
            deleted_synthetic = connection.execute(
                delete(tdm_synthetic_profiles_table)
            ).rowcount
            deleted_masking = connection.execute(
                delete(tdm_masking_rules_table)
            ).rowcount
            deleted_mappings = connection.execute(
                delete(tdm_service_mappings_table)
            ).rowcount
            deleted_columns = connection.execute(
                delete(tdm_columns_table)
            ).rowcount
            deleted_tables = connection.execute(delete(tdm_tables_table)).rowcount
            deleted_schemas = connection.execute(delete(tdm_schemas_table)).rowcount
        return {
            "deleted_tdm_schemas": max(0, int(deleted_schemas or 0)),
            "deleted_tdm_tables": max(0, int(deleted_tables or 0)),
            "deleted_tdm_columns": max(0, int(deleted_columns or 0)),
            "deleted_tdm_service_mappings": max(
                0,
                int(deleted_mappings or 0),
            ),
            "deleted_tdm_masking_rules": max(0, int(deleted_masking or 0)),
            "deleted_tdm_virtualization_artifacts": max(
                0,
                int(deleted_virtualization or 0),
            ),
            "deleted_tdm_synthetic_profiles": max(
                0,
                int(deleted_synthetic or 0),
            ),
        }