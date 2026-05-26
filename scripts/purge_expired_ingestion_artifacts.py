"""Purge expired async ingestion artifact metadata from PostgreSQL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    """Return repository root path for local script execution."""
    return Path(__file__).resolve().parents[1]


def _bootstrap_src_path() -> None:
    """Ensure the src-layout package is importable for this script."""
    src_dir = _repo_root() / "src"
    src_path = str(src_dir)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


_bootstrap_src_path()

from coderag.core.settings import SETTINGS, resolve_postgres_dsn
from coderag.storage.postgres_ingestion_artifact_store import (
    PostgresIngestionArtifactStore,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser used by the purge script."""
    return argparse.ArgumentParser(
        description=(
            "Delete expired ingestion artifact metadata and payload remnants "
            "from Postgres."
        )
    )


def purge_expired_uploaded_artifacts(postgres_dsn: str) -> int:
    """Run TTL purge through the Postgres-backed artifact store."""
    store = PostgresIngestionArtifactStore(postgres_dsn)
    return store.purge_expired_uploaded_artifacts()


def main() -> int:
    """CLI entrypoint."""
    build_parser().parse_args()
    postgres_dsn = resolve_postgres_dsn(SETTINGS)
    if not postgres_dsn:
        print(
            "POSTGRES_* no esta configurado; no se ejecuto la purga TTL.",
            file=sys.stderr,
        )
        return 2

    purged_artifacts = purge_expired_uploaded_artifacts(postgres_dsn)
    print(
        json.dumps(
            {"purged_artifacts": purged_artifacts},
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())