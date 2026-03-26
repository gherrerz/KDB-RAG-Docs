"""Graph storage adapter with optional Neo4j support."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

from coderag.core.models import GraphPath
from coderag.core.settings import SETTINGS

ENTITY_PATTERN = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")


class GraphStore:
    """Bridge for graph persistence and traversal.

    When Neo4j is disabled or unavailable, methods become no-ops and
    callers should rely on local fallback graph behavior.
    """

    def __init__(self) -> None:
        self._driver = None

    def is_enabled(self) -> bool:
        """Return whether Neo4j integration is configured."""
        return bool(SETTINGS.use_neo4j and SETTINGS.neo4j_uri)

    def _get_driver(self):
        """Lazy-create Neo4j driver when integration is enabled."""
        if not self.is_enabled():
            return None
        if self._driver is not None:
            return self._driver

        try:
            from neo4j import GraphDatabase
        except Exception:
            return None

        auth = None
        if SETTINGS.neo4j_user and SETTINGS.neo4j_password:
            auth = (SETTINGS.neo4j_user, SETTINGS.neo4j_password)

        self._driver = GraphDatabase.driver(SETTINGS.neo4j_uri, auth=auth)
        return self._driver

    def replace_edges(
        self,
        source_id: str,
        edges: Iterable[Tuple[str, str, str, str, str]],
    ) -> None:
        """Replace edge set for one source in Neo4j."""
        driver = self._get_driver()
        if driver is None:
            return

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

    def expand_paths(
        self,
        query: str,
        hops: int,
        max_paths: int,
    ) -> List[GraphPath]:
        """Expand multi-hop graph paths using Neo4j if available."""
        driver = self._get_driver()
        if driver is None:
            return []

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
