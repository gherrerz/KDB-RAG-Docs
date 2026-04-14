"""Graph storage adapter backed by mandatory Neo4j runtime."""

from __future__ import annotations

import re
import unicodedata
import time
from typing import Iterable, List, Optional, Tuple

from coderag.core.models import GraphPath
from coderag.core.settings import SETTINGS

ENTITY_PATTERN = re.compile(
    r"\b[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ\-]{2,}"
    r"(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ\-]{2,}){0,2}\b",
    re.UNICODE,
)
TOKEN_PATTERN = re.compile(r"\b[\w\-]{2,}\b", re.UNICODE)
TOKEN_STOPWORDS = {
    "a",
    "al",
    "como",
    "con",
    "cual",
    "cuanto",
    "cuantos",
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
    "sin",
    "sobre",
    "una",
    "uno",
    "un",
    "sus",
    "su",
    "y",
}
TDM_RELATIONSHIP_TYPES = {
    "USES_TABLE",
    "HAS_COLUMN",
    "HAS_PII_CLASS",
    "MASKED_BY",
    "EXPOSES_ENDPOINT",
    "BACKED_BY_SCHEMA",
}


def _normalize_token(token: str) -> str:
    """Normalize token for consistent comparison across accents/case."""
    lowered = token.casefold().strip("_-")
    if not lowered:
        return ""
    normalized = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


class GraphStore:
    """Bridge for graph persistence and traversal."""

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
        if not self.is_enabled():
            return {
                "batch_size": max(1, SETTINGS.neo4j_ingest_batch_size),
                "batches_written": 0,
                "rows_written": 0,
                "retries": 0,
            }
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
        if not self.is_enabled():
            return 0
        driver = self._get_driver()

        with driver.session() as session:
            result = session.run("MATCH ()-[r:RELATES_TO]-() DELETE r")
            summary = result.consume()
            return int(summary.counters.relationships_deleted)

    @staticmethod
    def _write_tdm_batch(tx_or_session, rows: List[dict[str, str]]) -> None:
        """Write one typed TDM relationship batch in Neo4j."""
        tx_or_session.run(
            """
            UNWIND $rows AS row
            MERGE (a:Entity {name: row.src})
            MERGE (b:Entity {name: row.tgt})
            MERGE (a)-[r:TDM_REL {
                source_id: row.source_id,
                relation_type: row.rel
            }]->(b)
            """,
            rows=rows,
        )

    def _write_tdm_batch_with_retries(
        self,
        session,
        rows: List[dict[str, str]],
    ) -> int:
        """Write one TDM edge batch with bounded retries."""
        retries_done = 0
        max_retries = max(0, SETTINGS.neo4j_ingest_max_retries)
        base_delay_ms = max(1, SETTINGS.neo4j_ingest_retry_delay_ms)

        while True:
            try:
                if hasattr(session, "execute_write"):
                    session.execute_write(self._write_tdm_batch, rows)
                else:
                    self._write_tdm_batch(session, rows)
                return retries_done
            except Exception:
                if retries_done >= max_retries:
                    raise
                retries_done += 1
                time.sleep((base_delay_ms * retries_done) / 1000.0)

    def replace_tdm_edges(
        self,
        source_id: str,
        typed_edges: Iterable[Tuple[str, str, str, str]],
    ) -> dict[str, int]:
        """Replace typed TDM edges for one source in Neo4j."""
        if not self.is_enabled():
            return {
                "batch_size": max(1, SETTINGS.neo4j_ingest_batch_size),
                "batches_written": 0,
                "rows_written": 0,
                "retries": 0,
            }
        driver = self._get_driver()

        edge_rows = list(typed_edges)
        with driver.session() as session:
            session.run(
                "MATCH ()-[r:TDM_REL {source_id: $source_id}]-() DELETE r",
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

            normalized_rows: List[dict[str, str]] = []
            for src, rel, tgt, src_id in edge_rows:
                relation = rel.strip().upper()
                if relation not in TDM_RELATIONSHIP_TYPES:
                    continue
                normalized_rows.append(
                    {
                        "src": src,
                        "rel": relation,
                        "tgt": tgt,
                        "source_id": src_id,
                    }
                )

            if not normalized_rows:
                return metrics

            for batch_rows in self._chunk_rows(
                normalized_rows,
                SETTINGS.neo4j_ingest_batch_size,
            ):
                metrics["retries"] += self._write_tdm_batch_with_retries(
                    session,
                    batch_rows,
                )
                metrics["batches_written"] += 1
                metrics["rows_written"] += len(batch_rows)
            return metrics

    def expand_tdm_paths(
        self,
        query: str,
        hops: int,
        max_paths: int,
        source_id: Optional[str] = None,
        rel_types: Optional[List[str]] = None,
    ) -> List[GraphPath]:
        """Expand typed TDM graph paths using relation filters when provided."""
        if not self.is_enabled():
            return []
        driver = self._get_driver()
        entities = self._resolve_entities_from_query_tokens(
            driver=driver,
            query=query,
            max_entities=max_paths,
            source_id=source_id,
        )
        if not entities:
            entities = list(dict.fromkeys(ENTITY_PATTERN.findall(query)))
        if not entities:
            return []

        normalized_rel_types: List[str] = []
        if rel_types:
            normalized_rel_types = [
                rel.strip().upper()
                for rel in rel_types
                if rel.strip().upper() in TDM_RELATIONSHIP_TYPES
            ]

        hop_count = max(1, min(hops, 4))
        cypher = (
            "MATCH p=(a:Entity)-[rels:TDM_REL*1.."
            f"{hop_count}"
            "]-(b:Entity) "
            "WHERE a.name IN $entities "
            "AND ($source_id IS NULL "
            "OR all(r IN rels WHERE r.source_id = $source_id)) "
            "AND (size($rel_types) = 0 "
            "OR all(r IN rels WHERE r.relation_type IN $rel_types)) "
            "RETURN [n IN nodes(p) | n.name] AS nodes, "
            "[r IN relationships(p) | r.relation_type] AS relationships "
            "LIMIT $limit"
        )

        paths: List[GraphPath] = []
        with driver.session() as session:
            records = session.run(
                cypher,
                entities=entities,
                source_id=source_id,
                rel_types=normalized_rel_types,
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

    def expand_paths(
        self,
        query: str,
        hops: int,
        max_paths: int,
        source_id: Optional[str] = None,
    ) -> List[GraphPath]:
        """Expand multi-hop graph paths using Neo4j runtime."""
        if not self.is_enabled():
            return []
        driver = self._get_driver()

        entities = list(dict.fromkeys(ENTITY_PATTERN.findall(query)))
        if not entities:
            entities = self._resolve_entities_from_query_tokens(
                driver=driver,
                query=query,
                max_entities=max_paths,
                source_id=source_id,
            )
        if not entities:
            return []

        hop_count = max(1, min(hops, 4))
        cypher = (
            "MATCH p=(a:Entity)-[rels:RELATES_TO*1.."
            f"{hop_count}"
            "]-(b:Entity) "
            "WHERE a.name IN $entities "
            "AND ($source_id IS NULL "
            "OR all(r IN rels WHERE r.source_id = $source_id)) "
            "RETURN [n IN nodes(p) | n.name] AS nodes, "
            "[r IN relationships(p) | type(r)] AS relationships "
            "LIMIT $limit"
        )

        paths: List[GraphPath] = []
        with driver.session() as session:
            records = session.run(
                cypher,
                entities=entities,
                source_id=source_id,
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
            _normalize_token(token)
            for token in TOKEN_PATTERN.findall(query)
            if _normalize_token(token) not in TOKEN_STOPWORDS
        ]
        return [token for token in dict.fromkeys(tokens) if token]

    def _resolve_entities_from_query_tokens(
        self,
        driver,
        query: str,
        max_entities: int,
        source_id: Optional[str] = None,
    ) -> List[str]:
        """Resolve likely entity names from lowercase query tokens."""
        tokens = self._query_tokens(query)
        if not tokens:
            return []

        cypher = (
            "MATCH (e:Entity)-[r:RELATES_TO]-() "
            "WHERE any(token IN $tokens WHERE "
            "toLower(e.name) CONTAINS token) "
            "AND ($source_id IS NULL OR r.source_id = $source_id) "
            "RETURN DISTINCT e.name AS name "
            "LIMIT $limit"
        )
        with driver.session() as session:
            records = session.run(
                cypher,
                tokens=tokens,
                source_id=source_id,
                limit=max(1, min(max_entities, 12)),
            )
            return [
                str(record.get("name"))
                for record in records
                if record.get("name")
            ]
