"""Runtime singletons used by UI and API in local deployments."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from coderag.core.settings import SETTINGS
from coderag.storage.metadata_store import MetadataStore


@dataclass
class RuntimeState:
    """Shared state for lightweight local execution."""

    store: MetadataStore = field(
        default_factory=lambda: MetadataStore(
            Path(SETTINGS.data_dir) / "metadata.db"
        )
    )


RUNTIME = RuntimeState()
