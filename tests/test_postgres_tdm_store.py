"""Unit tests for the PostgreSQL-backed TDM store."""

from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Any

from coderag.storage.postgres_schema import (
    tdm_columns_table,
    tdm_masking_rules_table,
    tdm_schemas_table,
    tdm_service_mappings_table,
    tdm_synthetic_profiles_table,
    tdm_tables_table,
    tdm_virtualization_artifacts_table,
)
from coderag.storage.postgres_tdm_store import PostgresTdmStore


def _build_test_postgres_dsn(default_db: str = "coderag_docs") -> str:
    """Build a DSN for tests from env vars without hardcoded credentials."""
    host = os.environ.get("POSTGRES_HOST", "localhost").strip() or "localhost"
    port = os.environ.get("POSTGRES_PORT", "5432").strip() or "5432"
    database = os.environ.get("POSTGRES_DB", default_db).strip() or default_db
    user = os.environ.get("POSTGRES_USER", "").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "").strip()

    if user and password:
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return f"postgresql://{host}:{port}/{database}"


_TEST_POSTGRES_DSN = _build_test_postgres_dsn()


class _FakeMappingsResult:
    """Minimal mappings result object for SQLAlchemy-style reads."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        """Store rows that should be returned by all()."""
        self._rows = rows

    def all(self) -> list[dict[str, Any]]:
        """Return all configured mapping rows."""
        return self._rows


class _FakeExecuteResult:
    """Minimal execute result object for reads and writes."""

    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        rowcount: int | None = None,
    ) -> None:
        """Configure mapping rows and optional rowcount for one execute call."""
        self._rows = rows or []
        self.rowcount = rowcount

    def mappings(self) -> _FakeMappingsResult:
        """Return rows in the shape expected by .mappings().all()."""
        return _FakeMappingsResult(self._rows)


class _FakeConnection:
    """Collect executed statements and replay configured results."""

    def __init__(self, results: list[_FakeExecuteResult]) -> None:
        """Store queued execute results for later replay."""
        self._results = list(results)
        self.statements: list[Any] = []

    def execute(self, statement: Any) -> _FakeExecuteResult:
        """Record the statement and return the next queued result."""
        self.statements.append(statement)
        if not self._results:
            return _FakeExecuteResult()
        return self._results.pop(0)


class _FakeSessionFactory:
    """Provide one fake connection through get_connection()."""

    def __init__(self, connection: _FakeConnection) -> None:
        """Retain the connection used by the store under test."""
        self.connection = connection

    @contextmanager
    def get_connection(self) -> Any:
        """Yield the fake connection as a context manager."""
        yield self.connection


def test_upsert_methods_target_expected_tdm_tables() -> None:
    """Each TDM upsert should emit one statement against the right table."""
    connection = _FakeConnection([_FakeExecuteResult() for _ in range(7)])
    store = PostgresTdmStore(
        _TEST_POSTGRES_DSN,
        session_factory=_FakeSessionFactory(connection),
    )

    store.upsert_tdm_schema("schema-1", "src-1", "billing", "public", {})
    store.upsert_tdm_table(
        "table-1",
        "src-1",
        "schema-1",
        "customers",
        "table",
        {},
    )
    store.upsert_tdm_column(
        "column-1",
        "src-1",
        "table-1",
        "customer_email",
        "varchar",
        False,
        "email",
        {},
    )
    store.upsert_tdm_service_mapping(
        "mapping-1",
        "src-1",
        "billing-api",
        "/v1/customers",
        "GET",
        "table-1",
        {},
    )
    store.upsert_tdm_masking_rule(
        "rule-1",
        "src-1",
        "mask-email",
        "tokenize",
        "column",
        "table-1",
        "column-1",
        10,
        {},
    )
    store.upsert_tdm_virtualization_artifact(
        "artifact-1",
        "src-1",
        "billing-api",
        "mock-template",
        {"endpoint": "/v1/customers"},
        {},
    )
    store.upsert_tdm_synthetic_profile(
        "profile-1",
        "src-1",
        "billing-smoke",
        "template",
        "table-1",
        {},
    )

    assert [statement.table.name for statement in connection.statements] == [
        tdm_schemas_table.name,
        tdm_tables_table.name,
        tdm_columns_table.name,
        tdm_service_mappings_table.name,
        tdm_masking_rules_table.name,
        tdm_virtualization_artifacts_table.name,
        tdm_synthetic_profiles_table.name,
    ]


def test_list_methods_normalize_tdm_rows() -> None:
    """List methods should normalize JSON payloads and boolean fields."""
    connection = _FakeConnection(
        [
            _FakeExecuteResult(
                rows=[
                    {
                        "schema_id": "schema-1",
                        "source_id": "src-1",
                        "database_name": "billing",
                        "schema_name": "public",
                        "metadata_json": {"owner": "qa"},
                    }
                ]
            ),
            _FakeExecuteResult(
                rows=[
                    {
                        "table_id": "table-1",
                        "source_id": "src-1",
                        "schema_id": "schema-1",
                        "table_name": "customers",
                        "table_type": "table",
                        "metadata_json": {"critical": True},
                    }
                ]
            ),
            _FakeExecuteResult(
                rows=[
                    {
                        "column_id": "column-1",
                        "source_id": "src-1",
                        "table_id": "table-1",
                        "column_name": "customer_email",
                        "data_type": "varchar",
                        "nullable": False,
                        "pii_class": "email",
                        "metadata_json": {},
                    }
                ]
            ),
            _FakeExecuteResult(
                rows=[
                    {
                        "mapping_id": "mapping-1",
                        "source_id": "src-1",
                        "service_name": "billing-api",
                        "endpoint": "/v1/customers",
                        "method": "GET",
                        "table_id": "table-1",
                        "metadata_json": {},
                    }
                ]
            ),
            _FakeExecuteResult(
                rows=[
                    {
                        "rule_id": "rule-1",
                        "source_id": "src-1",
                        "rule_name": "mask-email",
                        "policy_type": "tokenize",
                        "scope": "column",
                        "table_id": None,
                        "column_id": "column-1",
                        "priority": 10,
                        "metadata_json": {},
                    }
                ]
            ),
            _FakeExecuteResult(
                rows=[
                    {
                        "artifact_id": "artifact-1",
                        "source_id": "src-1",
                        "service_name": "billing-api",
                        "artifact_type": "mock-template",
                        "content_json": {"endpoint": "/v1/customers"},
                        "metadata_json": {"owner": "qa"},
                    }
                ]
            ),
            _FakeExecuteResult(
                rows=[
                    {
                        "profile_id": "profile-1",
                        "source_id": "src-1",
                        "profile_name": "billing-smoke",
                        "target_table_id": "table-1",
                        "strategy": "template",
                        "metadata_json": {"size": "small"},
                    }
                ]
            ),
        ]
    )
    store = PostgresTdmStore(
        _TEST_POSTGRES_DSN,
        session_factory=_FakeSessionFactory(connection),
    )

    assert store.list_tdm_schemas("src-1")[0]["database_name"] == "billing"
    assert store.list_tdm_tables("src-1")[0]["table_name"] == "customers"
    assert store.list_tdm_columns("src-1")[0]["nullable"] is False
    assert (
        store.list_tdm_service_mappings("src-1")[0]["service_name"]
        == "billing-api"
    )
    assert store.list_tdm_masking_rules("src-1")[0]["priority"] == 10
    assert (
        store.list_tdm_virtualization_artifacts("src-1")[0]["content"]
        == {"endpoint": "/v1/customers"}
    )
    assert (
        store.list_tdm_synthetic_profiles("src-1")[0]["target_table_id"]
        == "table-1"
    )


def test_clear_tdm_data_deletes_all_tdm_tables() -> None:
    """TDM cleanup should delete every TDM table in child-to-parent order."""
    connection = _FakeConnection(
        [
            _FakeExecuteResult(rowcount=1),
            _FakeExecuteResult(rowcount=2),
            _FakeExecuteResult(rowcount=3),
            _FakeExecuteResult(rowcount=4),
            _FakeExecuteResult(rowcount=5),
            _FakeExecuteResult(rowcount=6),
            _FakeExecuteResult(rowcount=7),
        ]
    )
    store = PostgresTdmStore(
        _TEST_POSTGRES_DSN,
        session_factory=_FakeSessionFactory(connection),
    )

    deleted = store.clear_tdm_data()

    assert deleted == {
        "deleted_tdm_schemas": 7,
        "deleted_tdm_tables": 6,
        "deleted_tdm_columns": 5,
        "deleted_tdm_service_mappings": 4,
        "deleted_tdm_masking_rules": 3,
        "deleted_tdm_virtualization_artifacts": 1,
        "deleted_tdm_synthetic_profiles": 2,
    }
    assert [statement.table.name for statement in connection.statements] == [
        tdm_virtualization_artifacts_table.name,
        tdm_synthetic_profiles_table.name,
        tdm_masking_rules_table.name,
        tdm_service_mappings_table.name,
        tdm_columns_table.name,
        tdm_tables_table.name,
        tdm_schemas_table.name,
    ]