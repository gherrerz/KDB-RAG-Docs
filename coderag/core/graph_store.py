"""Graph storage adapter backed by mandatory Neo4j runtime."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

from coderag.core.models import GraphPath
from coderag.core.settings import SETTINGS

ENTITY_PATTERN = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")


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

    def replace_edges(
        self,
        source_id: str,
        edges: Iterable[Tuple[str, str, str, str, str]],
    ) -> None:
        """Replace edge set for one source in Neo4j."""
        driver = self._get_driver()

        edge_rows = list(edges)
        with driver.session() as session:
            session.run(
                "MATCH ()-[r:RELATES_TO {source_id: $source_id}]-() DELETE r",
                source_id=source_id,
            )
            for _edge_id, src, relation, tgt, src_id in edge_rows:
                rel_type = relation if relation else "RELATES_TO"
                if rel_type != "RELATES_TO":
                    rel_type = "RELATES_TO"
                session.run(
                    """
                    MERGE (a:Entity {name: $src})
                    MERGE (b:Entity {name: $tgt})
                    MERGE (a)-[r:RELATES_TO {source_id: $source_id}]->(b)
                    """,
                    src=src,
                    tgt=tgt,
                    source_id=src_id,
                )

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
