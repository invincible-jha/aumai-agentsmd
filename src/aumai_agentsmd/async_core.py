"""Async API for aumai-agentsmd using aumai-async-core foundation library.

Provides AsyncAgentsMDService — a lifecycle-managed async service that wraps
the synchronous parser, validator, and generator with event emission,
concurrency control, and health checks.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aumai_async_core import AsyncEventEmitter, AsyncService, AsyncServiceConfig

from aumai_agentsmd.core import (
    AgentsMdGenerator,
    AgentsMdParser,
    AgentsMdValidator,
    generate_template,
)
from aumai_agentsmd.models import AgentsMdDocument, ValidationResult


class AsyncAgentsMDService(AsyncService):
    """Lifecycle-managed async service for AGENTS.md document operations.

    Wraps the synchronous :class:`~aumai_agentsmd.core.AgentsMdParser`,
    :class:`~aumai_agentsmd.core.AgentsMdValidator`, and
    :class:`~aumai_agentsmd.core.AgentsMdGenerator` with async-first
    ergonomics, event emission on document operations, and the full
    :class:`~aumai_async_core.core.AsyncService` lifecycle (start/stop,
    health checks, concurrency limits).

    Events emitted:
        - ``doc.generated``: fired after a document is generated from a
          template or an existing :class:`~aumai_agentsmd.models.AgentsMdDocument`.
          Payload keys: ``project_name``.
        - ``doc.validated``: fired after a document is validated.
          Payload keys: ``project_name``, ``valid``, ``issue_count``.
        - ``doc.parsed``: fired after raw markdown is parsed into a document.
          Payload keys: ``project_name``.

    Example::

        config = AsyncServiceConfig(name="agentsmd")
        service = AsyncAgentsMDService(config)
        await service.start()

        doc = await service.parse("# MyProject\\n\\n## Capabilities\\n\\n- Do things")

        @service.emitter.on_event("doc.validated")
        async def on_validated(project_name: str, valid: bool, **kw: Any) -> None:
            print(f"{project_name} valid={valid}")

        await service.stop()
    """

    def __init__(
        self,
        config: AsyncServiceConfig | None = None,
        *,
        run_in_executor: bool = True,
    ) -> None:
        """Initialise the async agentsmd service.

        Args:
            config: Service configuration.  Defaults to a sensible config
                with ``name="agentsmd"``.
            run_in_executor: When ``True`` (the default), CPU-bound parsing
                and validation runs in the default thread executor to avoid
                blocking the event loop.  Set to ``False`` in tests to keep
                execution synchronous.
        """
        effective_config = config or AsyncServiceConfig(
            name="agentsmd",
            health_check_interval_seconds=0.0,
        )
        super().__init__(effective_config)
        self._parser: AgentsMdParser = AgentsMdParser()
        self._validator: AgentsMdValidator = AgentsMdValidator()
        self._generator: AgentsMdGenerator = AgentsMdGenerator()
        self._emitter: AsyncEventEmitter = AsyncEventEmitter()
        self._run_in_executor = run_in_executor

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def emitter(self) -> AsyncEventEmitter:
        """The :class:`~aumai_async_core.events.AsyncEventEmitter` for this service.

        Register handlers here to receive ``doc.generated``, ``doc.validated``,
        and ``doc.parsed`` events.
        """
        return self._emitter

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def on_start(self) -> None:
        """Reinitialise the underlying sync components on service start."""
        self._parser = AgentsMdParser()
        self._validator = AgentsMdValidator()
        self._generator = AgentsMdGenerator()

    async def on_stop(self) -> None:
        """Remove all event listeners on service shutdown."""
        self._emitter.remove_all_listeners()

    async def health_check(self) -> bool:
        """Return ``True`` when the underlying parser is operational.

        A trivial probe — parse a minimal document and assert a non-empty
        project name results.
        """
        probe = "# HealthCheckProject\n\n## Project Context\n\nOK.\n"
        try:
            doc = self._parser.parse(probe)
            return doc.project_name != ""
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Core async API
    # ------------------------------------------------------------------

    async def parse(self, content: str) -> AgentsMdDocument:
        """Parse raw markdown *content* into a structured document asynchronously.

        The CPU-bound parsing work is dispatched to a thread executor so
        the event loop remains unblocked.  A ``doc.parsed`` event is emitted
        after parsing completes.

        Args:
            content: Raw AGENTS.md markdown string.

        Returns:
            A :class:`~aumai_agentsmd.models.AgentsMdDocument`.
        """
        await self.increment_request_count()

        try:
            if self._run_in_executor:
                loop = asyncio.get_running_loop()
                doc: AgentsMdDocument = await loop.run_in_executor(
                    None, self._parser.parse, content
                )
            else:
                doc = self._parser.parse(content)
        except Exception:
            await self.increment_error_count()
            raise

        await self._emitter.emit("doc.parsed", project_name=doc.project_name)
        return doc

    async def validate(self, doc: AgentsMdDocument) -> ValidationResult:
        """Validate *doc* asynchronously and emit a ``doc.validated`` event.

        Args:
            doc: A :class:`~aumai_agentsmd.models.AgentsMdDocument` to validate.

        Returns:
            A :class:`~aumai_agentsmd.models.ValidationResult` with issues and
            a ``valid`` flag.
        """
        await self.increment_request_count()

        try:
            if self._run_in_executor:
                loop = asyncio.get_running_loop()
                result: ValidationResult = await loop.run_in_executor(
                    None, self._validator.validate, doc
                )
            else:
                result = self._validator.validate(doc)
        except Exception:
            await self.increment_error_count()
            raise

        await self._emitter.emit(
            "doc.validated",
            project_name=doc.project_name,
            valid=result.valid,
            issue_count=len(result.issues),
        )
        return result

    async def generate(self, doc: AgentsMdDocument) -> str:
        """Render *doc* back to AGENTS.md markdown asynchronously.

        Emits a ``doc.generated`` event after the markdown is produced.

        Args:
            doc: A :class:`~aumai_agentsmd.models.AgentsMdDocument` to render.

        Returns:
            A markdown string.
        """
        await self.increment_request_count()

        try:
            if self._run_in_executor:
                loop = asyncio.get_running_loop()
                markdown: str = await loop.run_in_executor(
                    None, self._generator.generate, doc
                )
            else:
                markdown = self._generator.generate(doc)
        except Exception:
            await self.increment_error_count()
            raise

        await self._emitter.emit("doc.generated", project_name=doc.project_name)
        return markdown

    async def parse_and_validate(
        self, content: str
    ) -> tuple[AgentsMdDocument, ValidationResult]:
        """Parse *content* and immediately validate the resulting document.

        Convenience method combining :meth:`parse` and :meth:`validate` into a
        single call.

        Args:
            content: Raw AGENTS.md markdown string.

        Returns:
            A ``(document, validation_result)`` tuple.
        """
        doc = await self.parse(content)
        result = await self.validate(doc)
        return doc, result

    async def generate_from_template(self, project_name: str) -> str:
        """Generate a filled AGENTS.md template for *project_name* asynchronously.

        Emits a ``doc.generated`` event after the template is produced.

        Args:
            project_name: The name to embed in the generated template.

        Returns:
            A markdown string containing the filled template.
        """
        await self.increment_request_count()

        try:
            if self._run_in_executor:
                loop = asyncio.get_running_loop()
                markdown = await loop.run_in_executor(
                    None, generate_template, project_name
                )
            else:
                markdown = generate_template(project_name)
        except Exception:
            await self.increment_error_count()
            raise

        await self._emitter.emit("doc.generated", project_name=project_name)
        return markdown


__all__ = ["AsyncAgentsMDService"]
