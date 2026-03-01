"""LLM-powered documentation enricher using aumai-llm-core foundation library.

Provides LLMDocEnricher, which uses a language model to perform semantic
analysis of AGENTS.md documents — suggesting missing sections, improving
descriptions, and identifying quality gaps.  Falls back to a static
heuristic analysis when the LLM is unavailable.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from aumai_llm_core import (
    CompletionRequest,
    LLMClient,
    Message,
    MockProvider,
    ModelConfig,
)
from pydantic import BaseModel, Field

from aumai_agentsmd.models import AgentsMdDocument

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Structured output model
# ---------------------------------------------------------------------------

_QUALITY_LEVEL_VALUES = ("poor", "fair", "good", "excellent")


class EnrichmentResult(BaseModel):
    """Structured output returned by the LLM-powered document analysis.

    Attributes:
        quality_level: Overall documentation quality — one of ``"poor"``,
            ``"fair"``, ``"good"``, or ``"excellent"``.
        summary: Short natural-language summary of the document's strengths
            and weaknesses.
        missing_sections: List of standard AGENTS.md sections that are absent
            or underdeveloped.
        improvement_suggestions: Ordered list of actionable improvements.
        enriched_context: An improved rewrite of the project_context field,
            or an empty string when no improvement is suggested.
        llm_powered: ``True`` when the result came from an LLM call, ``False``
            when it came from the heuristic fallback.
    """

    quality_level: str = Field(
        default="fair",
        description="Overall quality: poor | fair | good | excellent",
    )
    summary: str = Field(
        default="",
        description="Human-readable summary of documentation quality.",
    )
    missing_sections: list[str] = Field(
        default_factory=list,
        description="Standard sections that are missing or empty.",
    )
    improvement_suggestions: list[str] = Field(
        default_factory=list,
        description="Ordered list of concrete improvement steps.",
    )
    enriched_context: str = Field(
        default="",
        description="Improved rewrite of the project context, or '' if fine.",
    )
    llm_powered: bool = Field(
        default=True,
        description="True when the result was produced by an LLM call.",
    )


# ---------------------------------------------------------------------------
# System prompt used for the LLM analysis
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a technical documentation specialist for AI agent projects.

Given a JSON representation of an AGENTS.md document, analyse it for
documentation quality and completeness.  Consider:
  - Whether the project context is clear and specific
  - Whether capabilities are concrete and actionable (not vague)
  - Whether constraints are enforceable and measurable
  - Whether scope boundaries are clearly defined
  - Whether the development workflow is complete and ordered
  - Whether any important sections are missing or underdeveloped

Respond ONLY with a valid JSON object matching this exact schema — no markdown,
no prose outside the JSON:
{
  "quality_level": "<poor|fair|good|excellent>",
  "summary": "<string>",
  "missing_sections": ["<section_name>", ...],
  "improvement_suggestions": ["<actionable improvement>", ...],
  "enriched_context": "<improved project context or empty string>"
}

Use "excellent" only when all sections are thorough and specific.
Use "poor" when multiple key sections are missing or nearly empty.
"""


class LLMDocEnricher:
    """LLM-powered enricher that performs semantic analysis of AGENTS.md documents.

    Sends the document to an LLM for deep analysis and returns a structured
    :class:`EnrichmentResult`.  Automatically falls back to heuristic-based
    analysis when the LLM call fails or the response cannot be parsed.

    Args:
        client: An :class:`~aumai_llm_core.core.LLMClient` instance.  When
            ``None`` the enricher operates in **fallback-only mode** (heuristic
            analysis only).

    Example (production)::

        config = ModelConfig(provider="anthropic", model_id="claude-sonnet-4-6")
        client = LLMClient(config)
        enricher = LLMDocEnricher(client=client)
        result = await enricher.analyze(doc)

    Example (testing with MockProvider)::

        enricher = build_mock_enricher()
        result = await enricher.analyze(doc)
        assert result.quality_level in ("poor", "fair", "good", "excellent")
    """

    def __init__(self, client: LLMClient | None = None) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(self, doc: AgentsMdDocument) -> EnrichmentResult:
        """Analyse *doc* for documentation quality using an LLM.

        The method first attempts an LLM call.  If the client is not
        configured, or if the LLM call fails, it falls back to heuristic
        analysis automatically.

        Args:
            doc: An :class:`~aumai_agentsmd.models.AgentsMdDocument` to analyse.

        Returns:
            An :class:`EnrichmentResult` with quality level, summary,
            missing sections, suggestions, and an optional enriched context.
        """
        if self._client is None:
            logger.debug(
                "LLMDocEnricher: no LLM client configured, using heuristic fallback."
            )
            return self._heuristic_fallback(doc)

        try:
            return await self._llm_analyze(doc)
        except Exception as exc:
            logger.warning(
                "LLMDocEnricher: LLM call failed (%s), falling back to heuristic.",
                exc,
            )
            return self._heuristic_fallback(doc)

    async def suggest_improvements(self, doc: AgentsMdDocument) -> list[str]:
        """Return a list of improvement suggestions for *doc*.

        Convenience wrapper around :meth:`analyze` that returns only the
        ``improvement_suggestions`` field.

        Args:
            doc: The document to analyse.

        Returns:
            List of actionable improvement suggestion strings.
        """
        result = await self.analyze(doc)
        return result.improvement_suggestions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _llm_analyze(self, doc: AgentsMdDocument) -> EnrichmentResult:
        """Perform the actual LLM call and parse the structured response.

        Args:
            doc: The document to analyse.

        Returns:
            Parsed :class:`EnrichmentResult`.

        Raises:
            Exception: Propagates any provider or JSON-parse errors so the
                caller can decide whether to fall back to heuristics.
        """
        doc_data = {
            "project_name": doc.project_name,
            "project_context": doc.project_context,
            "capabilities": doc.capabilities,
            "constraints": doc.constraints,
            "scope_boundaries": doc.scope_boundaries,
            "workflow_steps": doc.workflow_steps,
        }
        doc_json = json.dumps(doc_data, indent=2, ensure_ascii=False)
        user_message = (
            f"Analyse the following AGENTS.md document for quality and completeness:\n\n"
            f"```json\n{doc_json}\n```"
        )

        request = CompletionRequest(
            messages=[
                Message(role="system", content=_SYSTEM_PROMPT),
                Message(role="user", content=user_message),
            ],
            temperature=0.0,
        )

        assert self._client is not None  # guarded by caller
        response = await self._client.complete(request)
        return self._parse_llm_response(response.content)

    def _parse_llm_response(self, raw_content: str) -> EnrichmentResult:
        """Parse the LLM's JSON response into an :class:`EnrichmentResult`.

        Strips markdown code fences if present before attempting JSON parsing.
        If parsing fails, returns a conservative ``"fair"`` quality level
        with a note that the response was unparseable.

        Args:
            raw_content: Raw text content from the LLM response.

        Returns:
            An :class:`EnrichmentResult`.
        """
        content = raw_content.strip()
        # Strip optional markdown code fences.
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        try:
            data: dict[str, Any] = json.loads(content)
            quality_level = str(data.get("quality_level", "fair"))
            if quality_level not in _QUALITY_LEVEL_VALUES:
                quality_level = "fair"
            return EnrichmentResult(
                quality_level=quality_level,
                summary=str(data.get("summary", "")),
                missing_sections=list(data.get("missing_sections", [])),
                improvement_suggestions=list(data.get("improvement_suggestions", [])),
                enriched_context=str(data.get("enriched_context", "")),
                llm_powered=True,
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "LLMDocEnricher: could not parse LLM JSON response: %s", exc
            )
            return EnrichmentResult(
                quality_level="fair",
                summary=(
                    "LLM response could not be parsed — unable to assess quality. "
                    f"Parse error: {exc}"
                ),
                missing_sections=[],
                improvement_suggestions=["Manually review the AGENTS.md document."],
                enriched_context="",
                llm_powered=True,
            )

    def _heuristic_fallback(self, doc: AgentsMdDocument) -> EnrichmentResult:
        """Run heuristic analysis when the LLM is unavailable.

        Checks for empty or minimal sections and computes a quality level
        based on how many of the five standard sections are populated.

        Args:
            doc: The document to analyse.

        Returns:
            An :class:`EnrichmentResult` marked with ``llm_powered=False``.
        """
        missing: list[str] = []
        suggestions: list[str] = []

        if not doc.project_context:
            missing.append("project_context")
            suggestions.append("Add a project_context section describing the project purpose.")
        if not doc.capabilities:
            missing.append("capabilities")
            suggestions.append("Add at least 3 capability statements.")
        elif len(doc.capabilities) < 3:
            suggestions.append(
                f"Expand capabilities: only {len(doc.capabilities)} defined, aim for 3+."
            )
        if not doc.constraints:
            missing.append("constraints")
            suggestions.append("Add constraints to define what the agent must not do.")
        if not doc.scope_boundaries:
            missing.append("scope_boundaries")
            suggestions.append("Define clear in-scope and out-of-scope boundaries.")
        if not doc.workflow_steps:
            missing.append("development_workflow")
            suggestions.append("Add a step-by-step development workflow.")

        total_sections = 5
        populated = total_sections - len(missing)

        if populated == total_sections:
            quality = "good"
        elif populated >= 3:
            quality = "fair"
        else:
            quality = "poor"

        summary = (
            f"Heuristic analysis: {populated}/{total_sections} sections populated. "
            "LLM analysis was unavailable."
        )

        return EnrichmentResult(
            quality_level=quality,
            summary=summary,
            missing_sections=missing,
            improvement_suggestions=suggestions,
            enriched_context="",
            llm_powered=False,
        )


def build_mock_enricher(responses: list[str] | None = None) -> LLMDocEnricher:
    """Create an :class:`LLMDocEnricher` backed by a :class:`~aumai_llm_core.MockProvider`.

    This is the canonical way to build a fully testable LLM enricher without
    making real API calls.

    Args:
        responses: Canned JSON response strings to return in round-robin order.
            Defaults to a single ``"good"``-quality response.

    Returns:
        A configured :class:`LLMDocEnricher` using the mock provider.

    Example::

        enricher = build_mock_enricher([
            '{"quality_level":"excellent","summary":"Great doc","missing_sections":[],'
            '"improvement_suggestions":[],"enriched_context":""}'
        ])
        result = await enricher.analyze(doc)
        assert result.quality_level == "excellent"
    """
    default_response = json.dumps(
        {
            "quality_level": "good",
            "summary": "Document is well-structured.",
            "missing_sections": [],
            "improvement_suggestions": [],
            "enriched_context": "",
        }
    )
    effective_responses = responses if responses is not None else [default_response]

    mock_provider = MockProvider(responses=effective_responses)
    config = ModelConfig(provider="mock", model_id="mock-agentsmd-enricher")
    client = LLMClient(config)
    # Patch the provider directly — MockProvider is registered under "mock".
    client._provider = mock_provider  # type: ignore[attr-defined]
    return LLMDocEnricher(client=client)


__all__ = [
    "EnrichmentResult",
    "LLMDocEnricher",
    "build_mock_enricher",
]
