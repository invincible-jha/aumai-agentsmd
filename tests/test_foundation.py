"""Comprehensive tests for the four foundation modules in aumai-agentsmd.

Covers:
- async_core.py  — AsyncAgentsMDService lifecycle, events, parse/validate/generate
- store.py       — AgentsMDStore / StoredAgentDoc round-trips, queries, metrics
- llm_enricher.py — LLMDocEnricher analysis, heuristic fallback, MockProvider
- integration.py — AgentsMDIntegration registration, event publishing, auto-process
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from aumai_async_core import AsyncServiceConfig
from aumai_integration import AumOS, Event

from aumai_agentsmd.async_core import AsyncAgentsMDService
from aumai_agentsmd.integration import (
    AgentsMDIntegration,
    setup_agentsmd,
    _SERVICE_CAPABILITIES,
    _SERVICE_NAME,
    _SERVICE_VERSION,
)
from aumai_agentsmd.llm_enricher import (
    EnrichmentResult,
    LLMDocEnricher,
    build_mock_enricher,
)
from aumai_agentsmd.models import (
    AgentsMdDocument,
    ValidationResult,
)
from aumai_agentsmd.store import AgentsMDStore, StoredAgentDoc


# ===========================================================================
# Shared helpers and fixtures
# ===========================================================================


def _make_full_doc(project_name: str = "TestProject") -> AgentsMdDocument:
    """Return a fully-populated AgentsMdDocument."""
    return AgentsMdDocument(
        project_name=project_name,
        project_context="An AI agent that does amazing things.",
        capabilities=["Parse documents", "Validate schemas", "Generate reports"],
        constraints=["Must not call external APIs", "Must not store PII"],
        scope_boundaries=["In scope: agent logic", "Out of scope: UI"],
        workflow_steps=["Write test", "Implement", "Open PR"],
        raw_content="",
        extra_sections={},
    )


def _make_empty_doc(project_name: str = "EmptyProject") -> AgentsMdDocument:
    """Return a document with no section content."""
    return AgentsMdDocument(
        project_name=project_name,
        project_context="",
        capabilities=[],
        constraints=[],
        scope_boundaries=[],
        workflow_steps=[],
        raw_content="",
        extra_sections={},
    )


FULL_MARKDOWN = """\
# MyProject

## Project Context

This is the project context.

## Capabilities

- Parse AGENTS.md files
- Validate structure

## Constraints

- No external APIs

## Scope Boundaries

- In scope: core logic

## Development Workflow

1. Write test
2. Implement
"""

MINIMAL_MARKDOWN = """\
# TinyProject

## Project Context

A tiny project.

## Capabilities

- Do something

## Constraints

- Don't break things

## Scope Boundaries

- In scope: everything

## Development Workflow

1. Ship it
"""


def _make_async_service(name: str = "test-agentsmd") -> AsyncAgentsMDService:
    """Return an AsyncAgentsMDService with executor disabled for fast tests."""
    config = AsyncServiceConfig(name=name, health_check_interval_seconds=0.0)
    return AsyncAgentsMDService(config, run_in_executor=False)


# ===========================================================================
# StoredAgentDoc model tests
# ===========================================================================


class TestStoredAgentDoc:
    def test_default_id_is_uuid(self) -> None:
        record = StoredAgentDoc(project_name="P")
        assert uuid.UUID(record.id)

    def test_default_timestamp_is_iso(self) -> None:
        from datetime import datetime

        record = StoredAgentDoc(project_name="P")
        dt = datetime.fromisoformat(record.timestamp)
        assert dt is not None

    def test_default_valid_is_false(self) -> None:
        record = StoredAgentDoc(project_name="P")
        assert record.valid is False

    def test_default_issue_count_zero(self) -> None:
        record = StoredAgentDoc(project_name="P")
        assert record.issue_count == 0

    def test_default_doc_json_is_empty_obj(self) -> None:
        record = StoredAgentDoc(project_name="P")
        assert record.doc_json == "{}"

    def test_custom_fields_set_correctly(self) -> None:
        record = StoredAgentDoc(
            id="abc",
            project_name="Proj",
            valid=True,
            issue_count=2,
            doc_json='{"project_name":"Proj"}',
        )
        assert record.id == "abc"
        assert record.valid is True
        assert record.issue_count == 2

    def test_model_dump_has_all_keys(self) -> None:
        record = StoredAgentDoc(project_name="P")
        dumped = record.model_dump()
        for key in ("id", "project_name", "timestamp", "valid", "issue_count", "doc_json"):
            assert key in dumped

    def test_coerce_doc_json_from_dict(self) -> None:
        """model_validator must re-serialise when store returns dict instead of str."""
        record = StoredAgentDoc(
            project_name="P",
            doc_json={"project_name": "P", "capabilities": []},  # type: ignore[arg-type]
        )
        assert isinstance(record.doc_json, str)

    def test_to_document_round_trip(self) -> None:
        doc = _make_full_doc("RoundTrip")
        record = StoredAgentDoc(
            project_name=doc.project_name,
            doc_json=doc.model_dump_json(),
        )
        restored = record.to_document()
        assert restored.project_name == "RoundTrip"
        assert restored.capabilities == doc.capabilities

    def test_to_document_raises_on_invalid_json(self) -> None:
        record = StoredAgentDoc(project_name="P", doc_json="not-json")
        with pytest.raises(Exception):
            record.to_document()


# ===========================================================================
# AgentsMDStore lifecycle
# ===========================================================================


class TestAgentsMDStoreLifecycle:
    async def test_memory_factory_creates_store(self) -> None:
        store = AgentsMDStore.memory()
        assert isinstance(store, AgentsMDStore)

    async def test_initialize_allows_use(self) -> None:
        store = AgentsMDStore.memory()
        await store.initialize()
        records = await store.get_all()
        assert isinstance(records, list)
        await store.close()

    async def test_context_manager_initializes_and_closes(self) -> None:
        async with AgentsMDStore.memory() as store:
            records = await store.get_all()
            assert records == []

    async def test_uninitialized_raises_on_get_all(self) -> None:
        store = AgentsMDStore.memory()
        with pytest.raises(RuntimeError, match="not been initialised"):
            await store.get_all()

    async def test_initialize_is_idempotent(self) -> None:
        async with AgentsMDStore.memory() as store:
            await store.initialize()
            records = await store.get_all()
            assert records == []


# ===========================================================================
# AgentsMDStore save_document
# ===========================================================================


class TestAgentsMDStoreSaveDocument:
    async def test_save_returns_stored_record(self) -> None:
        async with AgentsMDStore.memory() as store:
            doc = _make_full_doc()
            record = await store.save_document(doc)
            assert isinstance(record, StoredAgentDoc)

    async def test_save_sets_project_name(self) -> None:
        async with AgentsMDStore.memory() as store:
            doc = _make_full_doc("NamedProject")
            record = await store.save_document(doc)
            assert record.project_name == "NamedProject"

    async def test_save_with_validation_result_sets_valid_true(self) -> None:
        async with AgentsMDStore.memory() as store:
            doc = _make_full_doc()
            vr = ValidationResult(valid=True, issues=[], document=doc)
            record = await store.save_document(doc, vr)
            assert record.valid is True

    async def test_save_with_validation_result_sets_issue_count(self) -> None:
        from aumai_agentsmd.models import AgentsSection, ValidationIssue

        async with AgentsMDStore.memory() as store:
            doc = _make_empty_doc()
            issue = ValidationIssue(
                section=AgentsSection.capabilities,
                severity="error",
                message="Missing capabilities",
            )
            vr = ValidationResult(valid=False, issues=[issue], document=doc)
            record = await store.save_document(doc, vr)
            assert record.issue_count == 1

    async def test_save_without_validation_result_valid_false(self) -> None:
        async with AgentsMDStore.memory() as store:
            doc = _make_full_doc()
            record = await store.save_document(doc)
            assert record.valid is False

    async def test_save_stores_doc_json_as_string(self) -> None:
        async with AgentsMDStore.memory() as store:
            doc = _make_full_doc()
            record = await store.save_document(doc)
            assert isinstance(record.doc_json, str)

    async def test_save_doc_json_is_valid_json(self) -> None:
        async with AgentsMDStore.memory() as store:
            doc = _make_full_doc()
            record = await store.save_document(doc)
            parsed = json.loads(record.doc_json)
            assert isinstance(parsed, dict)

    async def test_save_assigns_non_empty_id(self) -> None:
        async with AgentsMDStore.memory() as store:
            doc = _make_full_doc()
            record = await store.save_document(doc)
            assert len(record.id) > 0


# ===========================================================================
# AgentsMDStore query methods
# ===========================================================================


class TestAgentsMDStoreQueries:
    async def test_get_by_project_empty_when_none_saved(self) -> None:
        async with AgentsMDStore.memory() as store:
            records = await store.get_by_project("NoSuchProject")
            assert records == []

    async def test_get_by_project_filters_by_name(self) -> None:
        async with AgentsMDStore.memory() as store:
            await store.save_document(_make_full_doc("Alpha"))
            await store.save_document(_make_full_doc("Beta"))
            records = await store.get_by_project("Alpha")
            assert len(records) == 1
            assert records[0].project_name == "Alpha"

    async def test_get_by_project_multiple_records(self) -> None:
        async with AgentsMDStore.memory() as store:
            doc = _make_full_doc("Multi")
            await store.save_document(doc)
            await store.save_document(doc)
            records = await store.get_by_project("Multi")
            assert len(records) == 2

    async def test_get_by_project_sorted_newest_first(self) -> None:
        async with AgentsMDStore.memory() as store:
            doc = _make_full_doc("Sorted")
            await store.save_document(doc)
            await store.save_document(doc)
            records = await store.get_by_project("Sorted")
            timestamps = [r.timestamp for r in records]
            assert timestamps == sorted(timestamps, reverse=True)

    async def test_get_valid_docs_returns_only_valid(self) -> None:
        async with AgentsMDStore.memory() as store:
            full_doc = _make_full_doc("Valid")
            vr_valid = ValidationResult(valid=True, issues=[], document=full_doc)
            empty_doc = _make_empty_doc("Invalid")
            vr_invalid = ValidationResult(valid=False, issues=[], document=empty_doc)
            await store.save_document(full_doc, vr_valid)
            await store.save_document(empty_doc, vr_invalid)
            valid_records = await store.get_valid_docs()
            assert all(r.valid for r in valid_records)
            assert any(r.project_name == "Valid" for r in valid_records)

    async def test_get_invalid_docs_returns_only_invalid(self) -> None:
        async with AgentsMDStore.memory() as store:
            full_doc = _make_full_doc("Valid2")
            vr_valid = ValidationResult(valid=True, issues=[], document=full_doc)
            empty_doc = _make_empty_doc("Invalid2")
            vr_invalid = ValidationResult(valid=False, issues=[], document=empty_doc)
            await store.save_document(full_doc, vr_valid)
            await store.save_document(empty_doc, vr_invalid)
            invalid_records = await store.get_invalid_docs()
            assert all(not r.valid for r in invalid_records)

    async def test_get_by_id_returns_record(self) -> None:
        async with AgentsMDStore.memory() as store:
            doc = _make_full_doc("ById")
            saved = await store.save_document(doc)
            retrieved = await store.get_by_id(saved.id)
            assert retrieved is not None
            assert retrieved.project_name == "ById"

    async def test_get_by_id_returns_none_for_unknown(self) -> None:
        async with AgentsMDStore.memory() as store:
            result = await store.get_by_id("non-existent-id")
            assert result is None

    async def test_get_all_returns_all_records(self) -> None:
        async with AgentsMDStore.memory() as store:
            await store.save_document(_make_full_doc("A"))
            await store.save_document(_make_full_doc("B"))
            all_records = await store.get_all()
            assert len(all_records) == 2

    async def test_get_all_empty_store(self) -> None:
        async with AgentsMDStore.memory() as store:
            assert await store.get_all() == []

    async def test_get_recent_limits_results(self) -> None:
        async with AgentsMDStore.memory() as store:
            doc = _make_full_doc("Paginated")
            for _ in range(8):
                await store.save_document(doc)
            records = await store.get_recent("Paginated", limit=3)
            assert len(records) == 3

    async def test_get_recent_default_limit_fifty(self) -> None:
        async with AgentsMDStore.memory() as store:
            doc = _make_full_doc("DefaultLimit")
            for _ in range(5):
                await store.save_document(doc)
            records = await store.get_recent("DefaultLimit")
            assert len(records) == 5


# ===========================================================================
# AgentsMDStore metrics
# ===========================================================================


class TestAgentsMDStoreMetrics:
    async def test_metrics_empty_store(self) -> None:
        async with AgentsMDStore.memory() as store:
            metrics = await store.compute_metrics()
            assert metrics["total"] == 0
            assert metrics["valid"] == 0
            assert metrics["invalid"] == 0
            assert metrics["valid_pct"] == 0.0

    async def test_metrics_all_valid(self) -> None:
        async with AgentsMDStore.memory() as store:
            doc = _make_full_doc("M")
            vr = ValidationResult(valid=True, issues=[], document=doc)
            for _ in range(4):
                await store.save_document(doc, vr)
            metrics = await store.compute_metrics()
            assert metrics["total"] == 4
            assert metrics["valid"] == 4
            assert metrics["valid_pct"] == 100.0

    async def test_metrics_mixed_valid_invalid(self) -> None:
        async with AgentsMDStore.memory() as store:
            valid_doc = _make_full_doc("V")
            invalid_doc = _make_empty_doc("I")
            vr_v = ValidationResult(valid=True, issues=[], document=valid_doc)
            vr_i = ValidationResult(valid=False, issues=[], document=invalid_doc)
            await store.save_document(valid_doc, vr_v)
            await store.save_document(valid_doc, vr_v)
            await store.save_document(invalid_doc, vr_i)
            metrics = await store.compute_metrics()
            assert metrics["total"] == 3
            assert metrics["valid"] == 2
            assert metrics["invalid"] == 1


# ===========================================================================
# AsyncAgentsMDService lifecycle
# ===========================================================================


class TestAsyncAgentsMDServiceLifecycle:
    async def test_default_config_name_is_agentsmd(self) -> None:
        service = AsyncAgentsMDService()
        assert service.config.name == "agentsmd"

    async def test_custom_config_respected(self) -> None:
        config = AsyncServiceConfig(name="custom-agentsmd", health_check_interval_seconds=0.0)
        service = AsyncAgentsMDService(config)
        assert service.config.name == "custom-agentsmd"

    async def test_service_starts_and_stops(self) -> None:
        service = _make_async_service()
        await service.start()
        assert service.status.state == "running"
        await service.stop()
        assert service.status.state == "stopped"

    async def test_initial_state_is_created(self) -> None:
        service = _make_async_service()
        assert service.status.state == "created"

    async def test_stop_removes_all_event_listeners(self) -> None:
        service = _make_async_service()
        await service.start()

        async def noop(**kw: Any) -> None:
            pass

        service.emitter.on("doc.parsed", noop)
        assert service.emitter.listener_count("doc.parsed") == 1
        await service.stop()
        assert service.emitter.listener_count("doc.parsed") == 0

    async def test_health_check_returns_true(self) -> None:
        service = _make_async_service()
        await service.start()
        result = await service.health_check()
        assert result is True
        await service.stop()

    async def test_emitter_property_is_event_emitter(self) -> None:
        from aumai_async_core import AsyncEventEmitter

        service = _make_async_service()
        assert isinstance(service.emitter, AsyncEventEmitter)


# ===========================================================================
# AsyncAgentsMDService — parse()
# ===========================================================================


class TestAsyncServiceParse:
    async def test_parse_returns_document(self) -> None:
        service = _make_async_service()
        await service.start()
        doc = await service.parse(FULL_MARKDOWN)
        assert isinstance(doc, AgentsMdDocument)
        await service.stop()

    async def test_parse_extracts_project_name(self) -> None:
        service = _make_async_service()
        await service.start()
        doc = await service.parse(FULL_MARKDOWN)
        assert doc.project_name == "MyProject"
        await service.stop()

    async def test_parse_emits_doc_parsed_event(self) -> None:
        service = _make_async_service()
        await service.start()
        events: list[dict[str, Any]] = []

        async def capture(**kw: Any) -> None:
            events.append(kw)

        service.emitter.on("doc.parsed", capture)
        await service.parse(FULL_MARKDOWN)
        assert len(events) == 1
        assert events[0]["project_name"] == "MyProject"
        await service.stop()

    async def test_parse_increments_request_count(self) -> None:
        service = _make_async_service()
        await service.start()
        await service.parse(FULL_MARKDOWN)
        assert service.status.request_count == 1
        await service.stop()

    async def test_parse_extracts_capabilities(self) -> None:
        service = _make_async_service()
        await service.start()
        doc = await service.parse(FULL_MARKDOWN)
        assert len(doc.capabilities) >= 1
        await service.stop()


# ===========================================================================
# AsyncAgentsMDService — validate()
# ===========================================================================


class TestAsyncServiceValidate:
    async def test_validate_returns_validation_result(self) -> None:
        service = _make_async_service()
        await service.start()
        doc = _make_full_doc()
        result = await service.validate(doc)
        assert isinstance(result, ValidationResult)
        await service.stop()

    async def test_validate_full_doc_is_valid(self) -> None:
        service = _make_async_service()
        await service.start()
        doc = _make_full_doc()
        result = await service.validate(doc)
        assert result.valid is True
        await service.stop()

    async def test_validate_empty_doc_is_not_valid(self) -> None:
        service = _make_async_service()
        await service.start()
        doc = _make_empty_doc()
        result = await service.validate(doc)
        assert result.valid is False
        await service.stop()

    async def test_validate_emits_doc_validated_event(self) -> None:
        service = _make_async_service()
        await service.start()
        events: list[dict[str, Any]] = []

        async def capture(**kw: Any) -> None:
            events.append(kw)

        service.emitter.on("doc.validated", capture)
        doc = _make_full_doc("ValidProject")
        await service.validate(doc)
        assert len(events) == 1
        assert events[0]["project_name"] == "ValidProject"
        assert "valid" in events[0]
        assert "issue_count" in events[0]
        await service.stop()

    async def test_validate_event_has_correct_valid_flag(self) -> None:
        service = _make_async_service()
        await service.start()
        events: list[dict[str, Any]] = []

        async def capture(**kw: Any) -> None:
            events.append(kw)

        service.emitter.on("doc.validated", capture)
        doc = _make_full_doc()
        await service.validate(doc)
        assert events[0]["valid"] is True
        await service.stop()

    async def test_validate_increments_request_count(self) -> None:
        service = _make_async_service()
        await service.start()
        doc = _make_full_doc()
        await service.validate(doc)
        assert service.status.request_count == 1
        await service.stop()


# ===========================================================================
# AsyncAgentsMDService — generate()
# ===========================================================================


class TestAsyncServiceGenerate:
    async def test_generate_returns_string(self) -> None:
        service = _make_async_service()
        await service.start()
        doc = _make_full_doc()
        markdown = await service.generate(doc)
        assert isinstance(markdown, str)
        await service.stop()

    async def test_generate_contains_project_name(self) -> None:
        service = _make_async_service()
        await service.start()
        doc = _make_full_doc("GeneratedProject")
        markdown = await service.generate(doc)
        assert "GeneratedProject" in markdown
        await service.stop()

    async def test_generate_emits_doc_generated_event(self) -> None:
        service = _make_async_service()
        await service.start()
        events: list[dict[str, Any]] = []

        async def capture(**kw: Any) -> None:
            events.append(kw)

        service.emitter.on("doc.generated", capture)
        doc = _make_full_doc("GenEvent")
        await service.generate(doc)
        assert len(events) == 1
        assert events[0]["project_name"] == "GenEvent"
        await service.stop()

    async def test_generate_increments_request_count(self) -> None:
        service = _make_async_service()
        await service.start()
        doc = _make_full_doc()
        await service.generate(doc)
        assert service.status.request_count == 1
        await service.stop()


# ===========================================================================
# AsyncAgentsMDService — parse_and_validate()
# ===========================================================================


class TestAsyncServiceParseAndValidate:
    async def test_parse_and_validate_returns_tuple(self) -> None:
        service = _make_async_service()
        await service.start()
        doc, result = await service.parse_and_validate(FULL_MARKDOWN)
        assert isinstance(doc, AgentsMdDocument)
        assert isinstance(result, ValidationResult)
        await service.stop()

    async def test_parse_and_validate_full_md_is_valid(self) -> None:
        service = _make_async_service()
        await service.start()
        _doc, result = await service.parse_and_validate(FULL_MARKDOWN)
        assert result.valid is True
        await service.stop()

    async def test_parse_and_validate_emits_both_events(self) -> None:
        service = _make_async_service()
        await service.start()
        parsed_events: list[dict[str, Any]] = []
        validated_events: list[dict[str, Any]] = []

        async def on_parsed(**kw: Any) -> None:
            parsed_events.append(kw)

        async def on_validated(**kw: Any) -> None:
            validated_events.append(kw)

        service.emitter.on("doc.parsed", on_parsed)
        service.emitter.on("doc.validated", on_validated)
        await service.parse_and_validate(FULL_MARKDOWN)
        assert len(parsed_events) == 1
        assert len(validated_events) == 1
        await service.stop()


# ===========================================================================
# AsyncAgentsMDService — generate_from_template()
# ===========================================================================


class TestAsyncServiceGenerateTemplate:
    async def test_generate_from_template_returns_string(self) -> None:
        service = _make_async_service()
        await service.start()
        markdown = await service.generate_from_template("MyTemplateProject")
        assert isinstance(markdown, str)
        await service.stop()

    async def test_generate_from_template_contains_project_name(self) -> None:
        service = _make_async_service()
        await service.start()
        markdown = await service.generate_from_template("TemplateNameCheck")
        assert "TemplateNameCheck" in markdown
        await service.stop()

    async def test_generate_from_template_emits_doc_generated(self) -> None:
        service = _make_async_service()
        await service.start()
        events: list[dict[str, Any]] = []

        async def capture(**kw: Any) -> None:
            events.append(kw)

        service.emitter.on("doc.generated", capture)
        await service.generate_from_template("TemplateEvent")
        assert len(events) == 1
        assert events[0]["project_name"] == "TemplateEvent"
        await service.stop()


# ===========================================================================
# EnrichmentResult model tests
# ===========================================================================


class TestEnrichmentResult:
    def test_default_quality_level(self) -> None:
        result = EnrichmentResult()
        assert result.quality_level == "fair"

    def test_default_llm_powered_true(self) -> None:
        result = EnrichmentResult()
        assert result.llm_powered is True

    def test_set_all_fields(self) -> None:
        result = EnrichmentResult(
            quality_level="excellent",
            summary="Great doc",
            missing_sections=[],
            improvement_suggestions=["Add more context"],
            enriched_context="Better context here",
            llm_powered=False,
        )
        assert result.quality_level == "excellent"
        assert result.summary == "Great doc"
        assert result.llm_powered is False

    def test_default_lists_are_empty(self) -> None:
        result = EnrichmentResult()
        assert result.missing_sections == []
        assert result.improvement_suggestions == []

    def test_default_enriched_context_is_empty_str(self) -> None:
        result = EnrichmentResult()
        assert result.enriched_context == ""


# ===========================================================================
# LLMDocEnricher — heuristic fallback
# ===========================================================================


class TestLLMDocEnricherHeuristicFallback:
    async def test_no_client_uses_fallback(self) -> None:
        enricher = LLMDocEnricher(client=None)
        doc = _make_full_doc()
        result = await enricher.analyze(doc)
        assert result.llm_powered is False

    async def test_full_doc_quality_is_good_or_excellent(self) -> None:
        enricher = LLMDocEnricher(client=None)
        result = await enricher.analyze(_make_full_doc())
        assert result.quality_level in ("good", "excellent")

    async def test_empty_doc_quality_is_poor(self) -> None:
        enricher = LLMDocEnricher(client=None)
        result = await enricher.analyze(_make_empty_doc())
        assert result.quality_level == "poor"

    async def test_empty_doc_has_missing_sections(self) -> None:
        enricher = LLMDocEnricher(client=None)
        result = await enricher.analyze(_make_empty_doc())
        assert len(result.missing_sections) > 0

    async def test_empty_doc_has_suggestions(self) -> None:
        enricher = LLMDocEnricher(client=None)
        result = await enricher.analyze(_make_empty_doc())
        assert len(result.improvement_suggestions) > 0

    async def test_full_doc_no_missing_sections(self) -> None:
        enricher = LLMDocEnricher(client=None)
        result = await enricher.analyze(_make_full_doc())
        assert result.missing_sections == []

    async def test_summary_contains_section_count(self) -> None:
        enricher = LLMDocEnricher(client=None)
        result = await enricher.analyze(_make_full_doc())
        assert "/" in result.summary

    async def test_suggest_improvements_returns_list(self) -> None:
        enricher = LLMDocEnricher(client=None)
        suggestions = await enricher.suggest_improvements(_make_empty_doc())
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0

    async def test_suggest_improvements_full_doc_empty_list(self) -> None:
        enricher = LLMDocEnricher(client=None)
        suggestions = await enricher.suggest_improvements(_make_full_doc())
        assert isinstance(suggestions, list)
        # Full doc may have 0 suggestions
        assert suggestions == [] or isinstance(suggestions[0], str)


# ===========================================================================
# LLMDocEnricher — MockProvider
# ===========================================================================


class TestLLMDocEnricherMockProvider:
    async def test_build_mock_enricher_returns_enricher(self) -> None:
        enricher = build_mock_enricher()
        assert isinstance(enricher, LLMDocEnricher)

    async def test_mock_enricher_default_response_good(self) -> None:
        enricher = build_mock_enricher()
        result = await enricher.analyze(_make_full_doc())
        assert result.quality_level == "good"
        assert result.llm_powered is True

    async def test_mock_enricher_custom_excellent_response(self) -> None:
        response = json.dumps(
            {
                "quality_level": "excellent",
                "summary": "Outstanding documentation.",
                "missing_sections": [],
                "improvement_suggestions": [],
                "enriched_context": "",
            }
        )
        enricher = build_mock_enricher(responses=[response])
        result = await enricher.analyze(_make_full_doc())
        assert result.quality_level == "excellent"
        assert result.summary == "Outstanding documentation."

    async def test_mock_enricher_poor_quality_response(self) -> None:
        response = json.dumps(
            {
                "quality_level": "poor",
                "summary": "Needs major work.",
                "missing_sections": ["capabilities", "constraints"],
                "improvement_suggestions": ["Add capabilities", "Add constraints"],
                "enriched_context": "",
            }
        )
        enricher = build_mock_enricher(responses=[response])
        result = await enricher.analyze(_make_empty_doc())
        assert result.quality_level == "poor"
        assert len(result.missing_sections) == 2

    async def test_mock_enricher_with_enriched_context(self) -> None:
        response = json.dumps(
            {
                "quality_level": "good",
                "summary": "Good overall.",
                "missing_sections": [],
                "improvement_suggestions": [],
                "enriched_context": "An improved context description.",
            }
        )
        enricher = build_mock_enricher(responses=[response])
        result = await enricher.analyze(_make_full_doc())
        assert result.enriched_context == "An improved context description."

    async def test_mock_enricher_invalid_json_falls_back(self) -> None:
        enricher = build_mock_enricher(responses=["this is not json at all"])
        result = await enricher.analyze(_make_full_doc())
        # Should produce a result (parse error fallback)
        assert isinstance(result, EnrichmentResult)
        assert result.llm_powered is True

    async def test_mock_enricher_invalid_quality_level_coerced_to_fair(self) -> None:
        response = json.dumps(
            {
                "quality_level": "amazing",  # not in allowed set
                "summary": "Test",
                "missing_sections": [],
                "improvement_suggestions": [],
                "enriched_context": "",
            }
        )
        enricher = build_mock_enricher(responses=[response])
        result = await enricher.analyze(_make_full_doc())
        assert result.quality_level == "fair"

    async def test_suggest_improvements_via_mock(self) -> None:
        response = json.dumps(
            {
                "quality_level": "fair",
                "summary": "Could be better.",
                "missing_sections": [],
                "improvement_suggestions": ["Add more detail", "Clarify scope"],
                "enriched_context": "",
            }
        )
        enricher = build_mock_enricher(responses=[response])
        suggestions = await enricher.suggest_improvements(_make_full_doc())
        assert suggestions == ["Add more detail", "Clarify scope"]


# ===========================================================================
# AgentsMDIntegration — registration
# ===========================================================================


@pytest.fixture
def aumos() -> AumOS:
    """Return a fresh AumOS instance for each test."""
    return AumOS()


@pytest.fixture
def integration(aumos: AumOS) -> AgentsMDIntegration:
    return AgentsMDIntegration.from_aumos(aumos)


class TestAgentsMDIntegrationRegistration:
    async def test_register_sets_is_registered_true(
        self, integration: AgentsMDIntegration
    ) -> None:
        assert integration.is_registered is False
        await integration.register()
        assert integration.is_registered is True

    async def test_register_is_idempotent(
        self, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        await integration.register()
        assert integration.is_registered is True

    async def test_register_adds_service_to_discovery(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        service = aumos.get_service(_SERVICE_NAME)
        assert service is not None

    async def test_registered_service_has_correct_name(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        service = aumos.get_service(_SERVICE_NAME)
        assert service is not None
        assert service.name == _SERVICE_NAME

    async def test_registered_service_has_correct_version(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        service = aumos.get_service(_SERVICE_NAME)
        assert service is not None
        assert service.version == _SERVICE_VERSION

    async def test_registered_service_has_all_capabilities(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        service = aumos.get_service(_SERVICE_NAME)
        assert service is not None
        for cap in _SERVICE_CAPABILITIES:
            assert cap in service.capabilities

    async def test_registered_service_status_healthy(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        service = aumos.get_service(_SERVICE_NAME)
        assert service is not None
        assert service.status == "healthy"

    async def test_unregister_sets_is_registered_false(
        self, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        await integration.unregister()
        assert integration.is_registered is False

    async def test_unregister_stops_auto_process(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        await integration.unregister()
        parsed_events: list[Event] = []

        async def capture(event: Event) -> None:
            parsed_events.append(event)

        aumos.events.subscribe("doc.parsed", capture)
        await aumos.events.publish_simple(
            "agent.doc_requested",
            source="test-agent",
            content=FULL_MARKDOWN,
        )
        assert len(parsed_events) == 0


# ===========================================================================
# AgentsMDIntegration — factory / setup
# ===========================================================================


class TestAgentsMDIntegrationFactory:
    def test_from_aumos_returns_integration(self, aumos: AumOS) -> None:
        result = AgentsMDIntegration.from_aumos(aumos)
        assert isinstance(result, AgentsMDIntegration)

    def test_from_aumos_binds_hub(self, aumos: AumOS) -> None:
        result = AgentsMDIntegration.from_aumos(aumos)
        assert result.aumos is aumos

    async def test_setup_agentsmd_returns_registered_integration(
        self, aumos: AumOS
    ) -> None:
        result = await setup_agentsmd(aumos)
        assert isinstance(result, AgentsMDIntegration)
        assert result.is_registered is True

    async def test_setup_agentsmd_registers_service(self, aumos: AumOS) -> None:
        await setup_agentsmd(aumos)
        service = aumos.get_service(_SERVICE_NAME)
        assert service is not None


# ===========================================================================
# AgentsMDIntegration — parse_and_publish
# ===========================================================================


class TestAgentsMDIntegrationParseAndPublish:
    async def test_parse_and_publish_returns_document(
        self, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        doc = await integration.parse_and_publish(FULL_MARKDOWN)
        assert isinstance(doc, AgentsMdDocument)

    async def test_parse_and_publish_extracts_project_name(
        self, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        doc = await integration.parse_and_publish(FULL_MARKDOWN)
        assert doc.project_name == "MyProject"

    async def test_parse_and_publish_emits_doc_parsed_event(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        events: list[Event] = []

        async def capture(event: Event) -> None:
            events.append(event)

        aumos.events.subscribe("doc.parsed", capture)
        await integration.parse_and_publish(FULL_MARKDOWN)
        assert len(events) == 1
        assert events[0].data["project_name"] == "MyProject"

    async def test_parse_and_publish_emits_doc_validated_event(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        events: list[Event] = []

        async def capture(event: Event) -> None:
            events.append(event)

        aumos.events.subscribe("doc.validated", capture)
        await integration.parse_and_publish(FULL_MARKDOWN)
        assert len(events) == 1
        assert "valid" in events[0].data
        assert "issue_count" in events[0].data

    async def test_parse_and_publish_full_doc_valid_true_in_event(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        events: list[Event] = []

        async def capture(event: Event) -> None:
            events.append(event)

        aumos.events.subscribe("doc.validated", capture)
        await integration.parse_and_publish(FULL_MARKDOWN)
        assert events[0].data["valid"] is True

    async def test_parse_and_publish_caches_validation(
        self, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        await integration.parse_and_publish(FULL_MARKDOWN)
        cached = integration.get_cached_validation("MyProject")
        assert cached is not None
        assert isinstance(cached, ValidationResult)

    async def test_capability_cache_property_returns_dict(
        self, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        await integration.parse_and_publish(FULL_MARKDOWN)
        cache = integration.capability_cache
        assert isinstance(cache, dict)
        assert "MyProject" in cache


# ===========================================================================
# AgentsMDIntegration — publish_doc_generated
# ===========================================================================


class TestAgentsMDIntegrationPublishDocGenerated:
    async def test_publish_doc_generated_emits_event(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        events: list[Event] = []

        async def capture(event: Event) -> None:
            events.append(event)

        aumos.events.subscribe("doc.generated", capture)
        await integration.publish_doc_generated("PublishedProject")
        assert len(events) == 1
        assert events[0].data["project_name"] == "PublishedProject"

    async def test_publish_doc_generated_source_is_agentsmd(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        events: list[Event] = []

        async def capture(event: Event) -> None:
            events.append(event)

        aumos.events.subscribe("doc.generated", capture)
        await integration.publish_doc_generated("P")
        assert events[0].source == _SERVICE_NAME


# ===========================================================================
# AgentsMDIntegration — auto-process on agent.doc_requested
# ===========================================================================


class TestAgentsMDIntegrationAutoProcess:
    async def test_doc_requested_event_triggers_auto_parse(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        parsed_events: list[Event] = []

        async def capture(event: Event) -> None:
            parsed_events.append(event)

        aumos.events.subscribe("doc.parsed", capture)
        await aumos.events.publish_simple(
            "agent.doc_requested",
            source="test-agent",
            content=FULL_MARKDOWN,
        )
        assert len(parsed_events) == 1
        assert parsed_events[0].data["project_name"] == "MyProject"

    async def test_doc_requested_also_triggers_validation_event(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        validated_events: list[Event] = []

        async def capture(event: Event) -> None:
            validated_events.append(event)

        aumos.events.subscribe("doc.validated", capture)
        await aumos.events.publish_simple(
            "agent.doc_requested",
            source="test-agent",
            content=FULL_MARKDOWN,
        )
        assert len(validated_events) == 1

    async def test_doc_requested_missing_content_skipped_gracefully(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        parsed_events: list[Event] = []

        async def capture(event: Event) -> None:
            parsed_events.append(event)

        aumos.events.subscribe("doc.parsed", capture)
        await aumos.events.publish_simple(
            "agent.doc_requested",
            source="agent",
        )
        assert len(parsed_events) == 0

    async def test_doc_requested_empty_content_skipped_gracefully(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        parsed_events: list[Event] = []

        async def capture(event: Event) -> None:
            parsed_events.append(event)

        aumos.events.subscribe("doc.parsed", capture)
        await aumos.events.publish_simple(
            "agent.doc_requested",
            source="agent",
            content="   ",
        )
        assert len(parsed_events) == 0

    async def test_doc_requested_non_string_content_skipped(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        parsed_events: list[Event] = []

        async def capture(event: Event) -> None:
            parsed_events.append(event)

        aumos.events.subscribe("doc.parsed", capture)
        await aumos.events.publish_simple(
            "agent.doc_requested",
            source="agent",
            content=12345,
        )
        assert len(parsed_events) == 0

    async def test_multiple_doc_requests_all_processed(
        self, aumos: AumOS, integration: AgentsMDIntegration
    ) -> None:
        await integration.register()
        parsed_events: list[Event] = []

        async def capture(event: Event) -> None:
            parsed_events.append(event)

        aumos.events.subscribe("doc.parsed", capture)
        for _ in range(3):
            await aumos.events.publish_simple(
                "agent.doc_requested",
                source="agent",
                content=MINIMAL_MARKDOWN,
            )
        assert len(parsed_events) == 3
