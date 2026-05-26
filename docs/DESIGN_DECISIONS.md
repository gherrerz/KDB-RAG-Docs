# Design Decisions

## Status

This document is the approved target contract for the KDB-RAG-Docs storage cutover.
It is the source of truth for implementation work starting with PR A1.

When this document conflicts with references elsewhere in the documentation that still
describe the current runtime, treat this document as authoritative for the target
architecture and the approved cutover scope.

## Target Runtime Contract

The final supported runtime for KDB-RAG-Docs is:

- Postgres for operational metadata and lexical retrieval support.
- Remote Chroma for vector storage and vector search.
- Neo4j for graph and TDM persistence.

The final runtime target excludes:

- SQLite as an operational metadata store.
- Embedded Chroma as an operational vector store.
- A persistent workspace directory as a runtime prerequisite.

## Cutover Scope Decisions

- New Postgres tables for Docs must use the `Tbl_Documents_` prefix.
- `path_or_url` must preserve the original document origin, never a staged path.
- Deduplication keeps the current semantic rule based on `title + content_type`.
- Historical migration from SQLite is out of scope. The agreed strategy is reset and re-ingest.
- Prolonged dual-write between old and new storage backends is out of scope.

## Staging And Async Decisions

- Local staging is allowed only as a temporary ingestion mechanism.
- Temporary staged files must be deleted after ingestion completes, both on success and on failure.
- Async ingestion for local-file sources must rehydrate from temporary artifacts stored in Postgres.
- Async ingestion must not require shared filesystem staging as a final runtime contract.
- After async processing completes, binary payloads must not remain persisted; only lightweight operational metadata may remain when needed for observability.

## Documentation Guidance During Cutover

- Some documentation pages still describe the current implementation state while the cutover is in progress.
- Until later PRs finish the implementation, documentation may contain both current-state and target-state notes.
- For architecture, configuration, and implementation planning, the target-state contract defined here is authoritative.
