"""Graph storage adapter backed by mandatory Neo4j runtime."""

from __future__ import annotations

import re
import time
from typing import Iterable, List, Optional, Tuple

from coderag.core.models import GraphPath
from coderag.core.settings import SETTINGS

ENTITY_PATTERN = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
TOKEN_PATTERN = re.compile(r"\b[a-zA-Z][a-zA-Z0-9_]{2,}\b")
TOKEN_STOPWORDS = {
    "como",
    "con",
    "cual",
    "cuales",
    "cuando",
    "de",
    "del",
    "el",
    "en",
    "es",
    "la",
    "las",
    "los",
    "para",
    "por",
    "que",
    "se",
    "una",
    "uno",
    "y",
}


class GraphStore:
    """Bridge for graph persistence and traversal.

    Neo4j is mandatory in runtime. Operations fail explicitly when
    configuration or connectivity is invalid.
    """

    def __init__(self) -> None:
        self._driver = None

    def close(self) -> None:
        """Close Neo4j driver when it was initialized."""
        if self._driver is None:
            return
        self._driver.close()
        self._driver = None

    def is_enabled(self) -> bool:
        """Return whether Neo4j integration is configured."""
        return bool(
            SETTINGS.use_neo4j
            and SETTINGS.neo4j_uri
            and SETTINGS.neo4j_user
            and SETTINGS.neo4j_password
        )

    def _get_driver(self):
        """Lazy-create Neo4j driver when integration is enabled."""
        if not self.is_enabled():
            raise RuntimeError(
                "Neo4j runtime is not fully configured. Set USE_NEO4J=true, "
                "NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD."
            )
        if self._driver is not None:
            return self._driver

        try:
            from neo4j import GraphDatabase
        except Exception as exc:
            raise RuntimeError("Neo4j driver is not available.") from exc

        auth = (SETTINGS.neo4j_user, SETTINGS.neo4j_password)

        self._driver = GraphDatabase.driver(SETTINGS.neo4j_uri, auth=auth)
        try:
            self._driver.verify_connectivity()
        except Exception as exc:
            self._driver.close()
            self._driver = None
            raise RuntimeError(
                "Neo4j connectivity check failed."
            ) from exc
        return self._driver

    @staticmethod
    def _chunk_rows(rows: List[dict[str, str]], size: int) -> Iterable[List[dict[str, str]]]:
        """Yield rows in bounded chunks for transaction-sized writes."""
        batch_size = max(1, size)
        for start in range(0, len(rows), batch_size):
            yield rows[start:start + batch_size]

    @staticmethod
    def _write_batch(tx_or_session, rows: List[dict[str, str]]) -> None:
        """Write one relationship batch using the active Neo4j context."""
        tx_or_session.run(
            """
            UNWIND $rows AS row
            MERGE (a:Entity {name: row.src})
            MERGE (b:Entity {name: row.tgt})
            MERGE (a)-[:RELATES_TO {source_id: row.source_id}]->(b)
            """,
            rows=rows,
        )

    def _write_batch_with_retries(
        self,
        session,
        rows: List[dict[str, str]],
    ) -> int:
        """Write one batch with bounded retries for transient failures."""
        retries_done = 0
        max_retries = max(0, SETTINGS.neo4j_ingest_max_retries)
        base_delay_ms = max(1, SETTINGS.neo4j_ingest_retry_delay_ms)

        while True:
            try:
                if hasattr(session, "execute_write"):
                    session.execute_write(self._write_batch, rows)
                else:
                    self._write_batch(session, rows)
                return retries_done
            except Exception:
                if retries_done >= max_retries:
                    raise
                retries_done += 1
                time.sleep((base_delay_ms * retries_done) / 1000.0)

    def replace_edges(
        self,
        source_id: str,
        edges: Iterable[Tuple[str, str, str, str, str]],
    ) -> dict[str, int]:
        """Replace edge set for one source in Neo4j."""
        driver = self._get_driver()

        edge_rows = list(edges)
        with driver.session() as session:
            session.run(
                "MATCH ()-[r:RELATES_TO {source_id: $source_id}]-() DELETE r",
                source_id=source_id,
            )

            metrics = {
                "batch_size": max(1, SETTINGS.neo4j_ingest_batch_size),
                "batches_written": 0,
                "rows_written": 0,
                "retries": 0,
            }
            if not edge_rows:
                return metrics

            normalized_rows = [
                {
                    "src": src,
                    "tgt": tgt,
                    "source_id": src_id,
                }
                for _edge_id, src, _relation, tgt, src_id in edge_rows
            ]

            for batch_rows in self._chunk_rows(
                normalized_rows,
                SETTINGS.neo4j_ingest_batch_size,
            ):
                metrics["retries"] += self._write_batch_with_retries(
                    session,
                    batch_rows,
                )
                metrics["batches_written"] += 1
                metrics["rows_written"] += len(batch_rows)
            return metrics

    def clear_all_edges(self) -> int:
        """Delete all RELATES_TO edges from Neo4j and return count."""
        driver = self._get_driver()

        with driver.session() as session:
            result = session.run("MATCH ()-[r:RELATES_TO]-() DELETE r")
            summary = result.consume()
            return int(summary.counters.relationships_deleted)

    def expand_paths(
        self,
        query: str,
        hops: int,
        max_paths: int,
    ) -> List[GraphPath]:
        """Expand multi-hop graph paths using Neo4j runtime."""
        driver = self._get_driver()

        entities = list(dict.fromkeys(ENTITY_PATTERN.findall(query)))
        if not entities:
            entities = self._resolve_entities_from_query_tokens(
                driver=driver,
                query=query,
                max_entities=max_paths,
            )
        if not entities:
            return []

        hop_count = max(1, min(hops, 4))
        cypher = (
            "MATCH p=(a:Entity)-[:RELATES_TO*1.."
            f"{hop_count}"
            "]-(b:Entity) "
            "WHERE a.name IN $entities "
            "RETURN [n IN nodes(p) | n.name] AS nodes, "
            "[r IN relationships(p) | type(r)] AS relationships "
            "LIMIT $limit"
        )

        paths: List[GraphPath] = []
        with driver.session() as session:
            records = session.run(
                cypher,
                entities=entities,
                limit=max_paths,
            )
            for record in records:
                nodes = record.get("nodes", [])
                relationships = record.get("relationships", [])
                if nodes and relationships:
                    paths.append(
                        GraphPath(
                            nodes=nodes,
                            relationships=relationships,
                        )
                    )
        return paths

    @staticmethod
    def _query_tokens(query: str) -> List[str]:
        """Extract normalized query tokens for entity seed fallback."""
        tokens = [
            token.lower()
            for token in TOKEN_PATTERN.findall(query)
            if token.lower() not in TOKEN_STOPWORDS
        ]
        return list(dict.fromkeys(tokens))

    def _resolve_entities_from_query_tokens(
        self,
        driver,
        query: str,
        max_entities: int,
    ) -> List[str]:
        """Resolve likely entity names from lowercase query tokens."""
        tokens = self._query_tokens(query)
        if not tokens:
            return []

        cypher = (
            "MATCH (e:Entity) "
            "WHERE any(token IN $tokens WHERE "
            "toLower(e.name) CONTAINS token) "
            "RETURN DISTINCT e.name AS name "
            "LIMIT $limit"
        )
        with driver.session() as session:
            records = session.run(
                cypher,
                tokens=tokens,
                limit=max(1, min(max_entities, 12)),
            )
            return [
                str(record.get("name"))
                for record in records
                if record.get("name")
            ]
