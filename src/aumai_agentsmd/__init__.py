"""AumAI Agentsmd — parse, validate, and generate AGENTS.md files."""

from aumai_agentsmd.async_core import AsyncAgentsMDService
from aumai_agentsmd.core import (
    AgentsMdGenerator,
    AgentsMdParser,
    AgentsMdValidator,
    ConfigExporter,
    generate_template,
)
from aumai_agentsmd.integration import AgentsMDIntegration, setup_agentsmd
from aumai_agentsmd.llm_enricher import (
    EnrichmentResult,
    LLMDocEnricher,
    build_mock_enricher,
)
from aumai_agentsmd.models import (
    AgentsMdDocument,
    AgentsSection,
    ValidationIssue,
    ValidationResult,
)
from aumai_agentsmd.store import AgentsMDStore, StoredAgentDoc

__version__ = "0.1.0"

__all__ = [
    # Core sync API
    "AgentsMdParser",
    "AgentsMdValidator",
    "AgentsMdGenerator",
    "ConfigExporter",
    "generate_template",
    # Models
    "AgentsMdDocument",
    "AgentsSection",
    "ValidationIssue",
    "ValidationResult",
    # Async service
    "AsyncAgentsMDService",
    # Store
    "AgentsMDStore",
    "StoredAgentDoc",
    # LLM enricher
    "LLMDocEnricher",
    "EnrichmentResult",
    "build_mock_enricher",
    # Integration
    "AgentsMDIntegration",
    "setup_agentsmd",
]
