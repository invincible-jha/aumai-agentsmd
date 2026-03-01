"""Persistence layer for aumai-agentsmd using aumai-store foundation library.

Provides AgentsMDStore — a repository-backed persistence service for agent
documentation records — and StoredAgentDoc, the Pydantic model persisted to
SQLite (or an in-memory backend during tests).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from aumai_store import Repository, Store, StoreConfig
from pydantic import BaseModel, Field, model_validator

from aumai_agentsmd.models import AgentsMdDocument, ValidationResult


class StoredAgentDoc(BaseModel):
    """Persisted representation of a single AGENTS.md document record.

    Attributes:
        id: Unique identifier for this record (UUID v4 string).
        project_name: Name of the project the document describes.
        timestamp: UTC datetime when the document was stored.
        valid: Whether the document passed validation (``True``/``False``).
        issue_count: Number of validation issues found.
        doc_json: Full JSON-serialised :class:`~aumai_agentsmd.models.AgentsMdDocument`.
            When read back from the store the backend may deserialise the JSON
            string into a dict; the validator re-serialises it to ensure this
            field is always a string.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_name: str
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
    valid: bool = Field(default=False)
    issue_count: int = Field(default=0, ge=0)
    doc_json: str = Field(default="{}")

    @model_validator(mode="before")
    @classmethod
    def _coerce_doc_json(cls, values: Any) -> Any:
        """Re-serialise doc_json when the store returns it as a dict.

        The aumai-store memory backend parses any JSON-string value that
        starts with ``{`` or ``[`` back into a Python object before handing
        it to Pydantic.  This validator ensures ``doc_json`` is always a
        ``str`` regardless of the roundtrip.
        """
        if isinstance(values, dict):
            dj = values.get("doc_json")
            if dj is not None and not isinstance(dj, str):
                values["doc_json"] = json.dumps(dj)
        return values

    def to_document(self) -> AgentsMdDocument:
        """Deserialise the stored JSON back to an :class:`~aumai_agentsmd.models.AgentsMdDocument`.

        Returns:
            The reconstructed :class:`~aumai_agentsmd.models.AgentsMdDocument`.

        Raises:
            ValueError: If ``doc_json`` contains invalid JSON or does not
                match the AgentsMdDocument schema.
        """
        data = json.loads(self.doc_json)
        return AgentsMdDocument.model_validate(data)


class AgentsMDStore:
    """Repository-backed store for AGENTS.md document records.

    Wraps a :class:`~aumai_store.core.Store` and exposes domain-specific
    query methods for document history and validation statistics.

    Use :meth:`memory` to create an in-memory instance suitable for unit
    tests.  For production pass a :class:`~aumai_store.models.StoreConfig`
    pointing at a SQLite (or Postgres) database.

    Example::

        async with AgentsMDStore.memory() as doc_store:
            record = await doc_store.save_document(doc, validation_result)
            history = await doc_store.get_by_project("MyProject")
    """

    def __init__(self, store: Store) -> None:
        """Initialise using an existing :class:`~aumai_store.core.Store`.

        Args:
            store: A configured (but not yet necessarily initialised) store.
        """
        self._store: Store = store
        self._repo: Repository[StoredAgentDoc] | None = None

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def memory(cls) -> "AgentsMDStore":
        """Create an in-memory AgentsMDStore for testing.

        Returns:
            A :class:`AgentsMDStore` backed by
            :class:`~aumai_store.backends.MemoryBackend`.
        """
        return cls(Store.memory())

    @classmethod
    def sqlite(
        cls, database_url: str = "sqlite:///aumai_agentsmd.db"
    ) -> "AgentsMDStore":
        """Create a SQLite-backed AgentsMDStore.

        Args:
            database_url: SQLite connection URL, e.g. ``"sqlite:///docs.db"``.

        Returns:
            A :class:`AgentsMDStore` backed by
            :class:`~aumai_store.backends.SQLiteBackend`.
        """
        config = StoreConfig(backend="sqlite", database_url=database_url)
        return cls(Store(config))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Open the backend connection and ensure the document table exists.

        Must be called before any data operations.  Idempotent — safe to call
        multiple times.
        """
        await self._store.initialize()
        repo: Repository[StoredAgentDoc] = self._store.repository(StoredAgentDoc)
        await repo.ensure_table()
        self._repo = repo

    async def close(self) -> None:
        """Close the underlying store connection."""
        if hasattr(self._store, "close"):
            await self._store.close()  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "AgentsMDStore":
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def save_document(
        self,
        doc: AgentsMdDocument,
        validation_result: ValidationResult | None = None,
    ) -> StoredAgentDoc:
        """Persist an AGENTS.md document record and return the saved record.

        Args:
            doc: The :class:`~aumai_agentsmd.models.AgentsMdDocument` to save.
            validation_result: Optional
                :class:`~aumai_agentsmd.models.ValidationResult`.  When
                provided, ``valid`` and ``issue_count`` are derived from it.
                Defaults to ``valid=False, issue_count=0``.

        Returns:
            The persisted :class:`StoredAgentDoc` (with assigned ``id``).

        Raises:
            RuntimeError: If the store has not been initialised.
        """
        self._assert_initialized()

        valid = validation_result.valid if validation_result is not None else False
        issue_count = (
            len(validation_result.issues) if validation_result is not None else 0
        )

        record = StoredAgentDoc(
            project_name=doc.project_name,
            valid=valid,
            issue_count=issue_count,
            doc_json=doc.model_dump_json(),
        )
        assigned_id = await self._repo.save(record)  # type: ignore[union-attr]
        record = record.model_copy(update={"id": assigned_id})
        return record

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    async def get_by_project(self, project_name: str) -> list[StoredAgentDoc]:
        """Return all records for the given project name, newest first.

        Args:
            project_name: The project name to filter by.

        Returns:
            List of :class:`StoredAgentDoc` instances sorted by timestamp
            descending.
        """
        self._assert_initialized()
        records = await self._repo.find(project_name=project_name)  # type: ignore[union-attr]
        return sorted(records, key=lambda r: r.timestamp, reverse=True)

    async def get_valid_docs(self) -> list[StoredAgentDoc]:
        """Return all records whose documents passed validation.

        Returns:
            List of :class:`StoredAgentDoc` where ``valid=True``.
        """
        self._assert_initialized()
        return await self._repo.find(valid=True)  # type: ignore[union-attr]

    async def get_invalid_docs(self) -> list[StoredAgentDoc]:
        """Return all records whose documents failed validation.

        Returns:
            List of :class:`StoredAgentDoc` where ``valid=False``.
        """
        self._assert_initialized()
        return await self._repo.find(valid=False)  # type: ignore[union-attr]

    async def get_by_id(self, record_id: str) -> StoredAgentDoc | None:
        """Fetch a single document record by its primary key.

        Args:
            record_id: UUID string assigned during :meth:`save_document`.

        Returns:
            The :class:`StoredAgentDoc`, or ``None`` if not found.
        """
        self._assert_initialized()
        return await self._repo.get(record_id)  # type: ignore[union-attr]

    async def get_all(self) -> list[StoredAgentDoc]:
        """Return every document record stored in the backend.

        Returns:
            All :class:`StoredAgentDoc` instances.
        """
        self._assert_initialized()
        return await self._repo.find()  # type: ignore[union-attr]

    async def get_recent(
        self, project_name: str, limit: int = 50
    ) -> list[StoredAgentDoc]:
        """Return the N most-recent records for a project, newest first.

        Args:
            project_name: The project name to look up.
            limit: Maximum number of records to return (default ``50``).

        Returns:
            List of :class:`StoredAgentDoc` limited to *limit* entries.
        """
        all_records = await self.get_by_project(project_name)
        return all_records[:limit]

    async def compute_metrics(self) -> dict[str, int | float]:
        """Compute high-level metrics across all stored documents.

        Returns:
            A dict with keys:
            - ``total``: total number of stored records.
            - ``valid``: number of valid records.
            - ``invalid``: number of invalid records.
            - ``valid_pct``: percentage of valid records (0–100).
        """
        self._assert_initialized()
        all_records = await self.get_all()
        total = len(all_records)
        valid = sum(1 for r in all_records if r.valid)
        invalid = total - valid
        valid_pct = round(valid / total * 100, 1) if total > 0 else 0.0
        return {
            "total": total,
            "valid": valid,
            "invalid": invalid,
            "valid_pct": valid_pct,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assert_initialized(self) -> None:
        """Raise if :meth:`initialize` has not been called."""
        if self._repo is None:
            raise RuntimeError(
                "AgentsMDStore has not been initialised. "
                "Call await store.initialize() or use it as an async context manager."
            )


__all__ = ["StoredAgentDoc", "AgentsMDStore"]
