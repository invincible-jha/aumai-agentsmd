"""AumOS integration module for aumai-agentsmd.

Registers agentsmd as a named service in the AumOS discovery layer,
publishes domain events (doc.generated, doc.validated, doc.parsed), and
subscribes to capability events for automatic document processing.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aumai_integration import AumOS, Event, EventBus, ServiceInfo

from aumai_agentsmd.core import AgentsMdParser, AgentsMdValidator
from aumai_agentsmd.models import AgentsMdDocument, ValidationResult

logger = logging.getLogger(__name__)

# Service metadata constants.
_SERVICE_NAME = "agentsmd"
_SERVICE_VERSION = "0.1.0"
_SERVICE_DESCRIPTION = (
    "AumAI AgentsMD — parse, validate, and generate AGENTS.md documentation files."
)
_SERVICE_CAPABILITIES = [
    "agents-md-parsing",
    "agents-md-validation",
    "agents-md-generation",
]


class AgentsMDIntegration:
    """AumOS integration facade for the agentsmd service.

    Handles service registration, event subscriptions, and event publishing.
    One instance per application is expected; obtain via :meth:`from_aumos`.

    Attributes:
        SERVICE_NAME: Constant string ``"agentsmd"`` used as the service key.

    Example::

        hub = AumOS()
        integration = AgentsMDIntegration.from_aumos(hub)
        await integration.register()

        # Publish a doc.generated event manually:
        await hub.events.publish_simple(
            "doc.generated",
            source="agentsmd",
            project_name="MyProject",
        )
    """

    SERVICE_NAME: str = _SERVICE_NAME

    def __init__(self, aumos: AumOS) -> None:
        """Initialise the integration against an AumOS hub.

        Args:
            aumos: The AumOS hub to register with and subscribe events on.
        """
        self._aumos = aumos
        self._parser = AgentsMdParser()
        self._validator = AgentsMdValidator()
        self._subscription_id: str | None = None
        self._registered: bool = False
        # Cache of project_name -> last ValidationResult for subscribed events.
        self._capability_cache: dict[str, ValidationResult] = {}

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_aumos(cls, aumos: AumOS) -> "AgentsMDIntegration":
        """Create an :class:`AgentsMDIntegration` bound to *aumos*.

        Args:
            aumos: The AumOS hub instance.

        Returns:
            A new :class:`AgentsMDIntegration`.
        """
        return cls(aumos)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register(self) -> None:
        """Register agentsmd with AumOS and start listening for agent events.

        Idempotent — calling this method more than once is safe.

        Steps:
            1. Register the service descriptor with the discovery layer.
            2. Subscribe to ``agent.doc_requested`` events for auto-processing.
        """
        if self._registered:
            logger.debug("AgentsMDIntegration: already registered, skipping.")
            return

        service_info = ServiceInfo(
            name=_SERVICE_NAME,
            version=_SERVICE_VERSION,
            description=_SERVICE_DESCRIPTION,
            capabilities=list(_SERVICE_CAPABILITIES),
            endpoints={},
            metadata={
                "supported_sections": [
                    "project_context",
                    "capabilities",
                    "constraints",
                    "scope_boundaries",
                    "development_workflow",
                ],
                "export_formats": ["markdown", "yaml", "json"],
            },
            status="healthy",
        )
        self._aumos.register(service_info)
        logger.info(
            "AgentsMDIntegration: registered service '%s' v%s with capabilities %s",
            _SERVICE_NAME,
            _SERVICE_VERSION,
            _SERVICE_CAPABILITIES,
        )

        # Subscribe to agent.doc_requested events.
        self._subscription_id = self._aumos.events.subscribe(
            pattern="agent.doc_requested",
            handler=self._handle_doc_requested,
            subscriber=_SERVICE_NAME,
        )
        logger.info(
            "AgentsMDIntegration: subscribed to 'agent.doc_requested' events "
            "(subscription_id=%s)",
            self._subscription_id,
        )

        self._registered = True

    async def unregister(self) -> None:
        """Unsubscribe from events and mark the service as not registered.

        Does not remove the service from the discovery layer (that is managed
        by the AumOS hub lifecycle).
        """
        if self._subscription_id is not None:
            self._aumos.events.unsubscribe(self._subscription_id)
            self._subscription_id = None
        self._registered = False
        logger.info("AgentsMDIntegration: unregistered.")

    # ------------------------------------------------------------------
    # Document processing
    # ------------------------------------------------------------------

    async def parse_and_publish(
        self,
        content: str,
        source: str = _SERVICE_NAME,
    ) -> AgentsMdDocument:
        """Parse an AGENTS.md string and publish ``doc.parsed`` + ``doc.validated`` events.

        Args:
            content: Raw AGENTS.md markdown string.
            source: Event source label (defaults to ``"agentsmd"``).

        Returns:
            The parsed :class:`~aumai_agentsmd.models.AgentsMdDocument`.
        """
        doc = self._parser.parse(content)

        await self._aumos.events.publish_simple(
            "doc.parsed",
            source=source,
            project_name=doc.project_name,
        )
        logger.info(
            "AgentsMDIntegration: parsed document for project '%s'",
            doc.project_name,
        )

        validation = self._validator.validate(doc)
        self._capability_cache[doc.project_name] = validation

        await self._aumos.events.publish_simple(
            "doc.validated",
            source=source,
            project_name=doc.project_name,
            valid=validation.valid,
            issue_count=len(validation.issues),
        )
        logger.info(
            "AgentsMDIntegration: validated document for project '%s' — valid=%s, issues=%d",
            doc.project_name,
            validation.valid,
            len(validation.issues),
        )

        return doc

    async def publish_doc_generated(
        self,
        project_name: str,
        source: str = _SERVICE_NAME,
    ) -> None:
        """Publish a ``doc.generated`` event for *project_name*.

        Args:
            project_name: The name of the project whose document was generated.
            source: Event source label (defaults to ``"agentsmd"``).
        """
        await self._aumos.events.publish_simple(
            "doc.generated",
            source=source,
            project_name=project_name,
        )
        logger.info(
            "AgentsMDIntegration: published doc.generated for project '%s'",
            project_name,
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _handle_doc_requested(self, event: Event) -> None:
        """Auto-parse a document when an agent requests processing.

        Expected event payload keys:
            - ``content`` (str): The raw AGENTS.md content to parse.

        Missing or invalid payloads are logged as warnings and skipped.

        Args:
            event: The ``agent.doc_requested`` event received from the bus.
        """
        content = event.data.get("content")

        if not isinstance(content, str) or not content.strip():
            logger.warning(
                "AgentsMDIntegration: received 'agent.doc_requested' event "
                "from '%s' without valid 'content' payload — skipping.",
                event.source,
            )
            return

        logger.info(
            "AgentsMDIntegration: auto-processing doc request from source '%s'",
            event.source,
        )
        await self.parse_and_publish(content=content, source=_SERVICE_NAME)

    # ------------------------------------------------------------------
    # Capability cache access
    # ------------------------------------------------------------------

    def get_cached_validation(
        self, project_name: str
    ) -> ValidationResult | None:
        """Return the most-recent cached validation result for *project_name*.

        Args:
            project_name: The project name to look up.

        Returns:
            The cached :class:`~aumai_agentsmd.models.ValidationResult`, or
            ``None`` if no validation has been performed for this project.
        """
        return self._capability_cache.get(project_name)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_registered(self) -> bool:
        """``True`` when the service has been registered with AumOS."""
        return self._registered

    @property
    def aumos(self) -> AumOS:
        """The AumOS hub this integration is bound to."""
        return self._aumos

    @property
    def capability_cache(self) -> dict[str, ValidationResult]:
        """The in-memory capability cache mapping project name to validation result."""
        return dict(self._capability_cache)


async def setup_agentsmd(aumos: AumOS) -> AgentsMDIntegration:
    """Convenience function: create and register an :class:`AgentsMDIntegration`.

    Args:
        aumos: The AumOS hub to register with.

    Returns:
        The registered :class:`AgentsMDIntegration` instance.

    Example::

        hub = AumOS()
        integration = await setup_agentsmd(hub)
    """
    integration = AgentsMDIntegration.from_aumos(aumos)
    await integration.register()
    return integration


__all__ = [
    "AgentsMDIntegration",
    "setup_agentsmd",
]
