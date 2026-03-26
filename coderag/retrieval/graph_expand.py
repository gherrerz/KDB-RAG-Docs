"""Multi-hop graph expansion based on query entities."""

from __future__ import annotations

import re
from typing import Iterable, List

import networkx as nx

from coderag.core.models import GraphPath

ENTITY_PATTERN = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")


def build_graph(edges: Iterable[tuple[str, str, str]]) -> nx.Graph:
    """Build undirected graph from edge triplets."""
    graph = nx.Graph()
    for source_node, relation, target_node in edges:
        graph.add_edge(source_node, target_node, relation=relation)
    return graph


def expand_paths(
    query: str,
    graph: nx.Graph,
    hops: int,
    max_paths: int = 6,
) -> List[GraphPath]:
    """Find graph paths connected to entities mentioned in query."""
    entities = list(dict.fromkeys(ENTITY_PATTERN.findall(query)))
    if not entities:
        entities = list(graph.nodes)[:3]

    paths: List[GraphPath] = []
    for source in entities:
        if source not in graph:
            continue
        for target in graph.nodes:
            if source == target:
                continue
            try:
                path = nx.shortest_path(graph, source=source, target=target)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            if len(path) - 1 > hops:
                continue
            relationships = []
            for idx in range(len(path) - 1):
                edge = graph.get_edge_data(path[idx], path[idx + 1])
                relationships.append(edge.get("relation", "RELATES_TO"))
            paths.append(GraphPath(nodes=path, relationships=relationships))
            if len(paths) >= max_paths:
                return paths
    return paths
