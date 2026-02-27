"""Comprehensive tests for aumai_agentsmd core module."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from aumai_agentsmd.core import (
    AgentsMdGenerator,
    AgentsMdParser,
    AgentsMdValidator,
    ConfigExporter,
    _extract_list_items,
    _extract_prose,
    generate_template,
)
from aumai_agentsmd.models import (
    AgentsMdDocument,
    AgentsSection,
    ValidationIssue,
    ValidationResult,
)

from conftest import (
    ALIAS_HEADING_MD,
    EXTRA_SECTION_MD,
    FULL_AGENTS_MD,
    H3_HEADING_MD,
    MINIMAL_AGENTS_MD,
    MISSING_ALL_SECTIONS_MD,
    MIXED_LIST_MD,
    NO_H1_MD,
    UNICODE_MD,
)


# ---------------------------------------------------------------------------
# Internal helper tests: _extract_list_items
# ---------------------------------------------------------------------------


class TestExtractListItems:
    """Tests for the _extract_list_items helper."""

    def test_dash_bullets(self) -> None:
        lines = ["- item one", "- item two"]
        assert _extract_list_items(lines) == ["item one", "item two"]

    def test_star_bullets(self) -> None:
        lines = ["* item one", "* item two"]
        assert _extract_list_items(lines) == ["item one", "item two"]

    def test_plus_bullets(self) -> None:
        lines = ["+ item one"]
        assert _extract_list_items(lines) == ["item one"]

    def test_numbered_list(self) -> None:
        lines = ["1. first", "2. second", "3. third"]
        assert _extract_list_items(lines) == ["first", "second", "third"]

    def test_mixed_bullets_and_numbered(self) -> None:
        lines = ["- bullet", "1. numbered"]
        assert _extract_list_items(lines) == ["bullet", "numbered"]

    def test_empty_lines_ignored(self) -> None:
        lines = ["- item", "", "  ", "- another"]
        result = _extract_list_items(lines)
        assert "item" in result
        assert "another" in result

    def test_non_list_lines_ignored(self) -> None:
        lines = ["Some prose text", "- list item", "More prose"]
        assert _extract_list_items(lines) == ["list item"]

    def test_empty_input(self) -> None:
        assert _extract_list_items([]) == []

    def test_leading_whitespace_in_lines(self) -> None:
        lines = ["  - indented item"]
        assert _extract_list_items(lines) == ["indented item"]

    def test_item_with_trailing_whitespace(self) -> None:
        lines = ["- item with trailing   "]
        result = _extract_list_items(lines)
        assert result == ["item with trailing"]

    def test_all_non_list_lines(self) -> None:
        lines = ["Prose only", "More prose", "## Heading"]
        assert _extract_list_items(lines) == []


# ---------------------------------------------------------------------------
# Internal helper tests: _extract_prose
# ---------------------------------------------------------------------------


class TestExtractProse:
    """Tests for the _extract_prose helper."""

    def test_basic_prose(self) -> None:
        lines = ["Some context text.", "More context here."]
        result = _extract_prose(lines)
        assert "Some context text." in result
        assert "More context here." in result

    def test_empty_lines_skipped(self) -> None:
        lines = ["First line.", "", "Second line."]
        result = _extract_prose(lines)
        assert "First line." in result
        assert "Second line." in result

    def test_headings_excluded(self) -> None:
        lines = ["## A heading", "Prose text."]
        result = _extract_prose(lines)
        assert "A heading" not in result
        assert "Prose text." in result

    def test_list_items_excluded(self) -> None:
        lines = ["- A bullet", "Prose only."]
        result = _extract_prose(lines)
        assert "A bullet" not in result
        assert "Prose only." in result

    def test_numbered_items_excluded(self) -> None:
        lines = ["1. Step one", "Prose only."]
        result = _extract_prose(lines)
        assert "Step one" not in result
        assert "Prose only." in result

    def test_empty_input(self) -> None:
        assert _extract_prose([]) == ""

    def test_all_list_lines_returns_empty(self) -> None:
        lines = ["- item one", "- item two"]
        assert _extract_prose(lines) == ""

    def test_joins_with_space(self) -> None:
        lines = ["First.", "Second."]
        result = _extract_prose(lines)
        assert result == "First. Second."


# ---------------------------------------------------------------------------
# AgentsMdParser tests
# ---------------------------------------------------------------------------


class TestAgentsMdParser:
    """Tests for AgentsMdParser.parse and parse_file."""

    @pytest.fixture()
    def parser(self) -> AgentsMdParser:
        return AgentsMdParser()

    def test_parse_full_document_project_name(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(FULL_AGENTS_MD)
        assert doc.project_name == "MyProject"

    def test_parse_full_document_capabilities(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(FULL_AGENTS_MD)
        assert "Parse AGENTS.md files" in doc.capabilities
        assert "Validate document structure" in doc.capabilities
        assert "Generate normalised markdown" in doc.capabilities

    def test_parse_full_document_constraints(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(FULL_AGENTS_MD)
        assert len(doc.constraints) == 2
        assert "Must not access external APIs without approval" in doc.constraints

    def test_parse_full_document_scope_boundaries(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(FULL_AGENTS_MD)
        assert "In scope: core agent logic" in doc.scope_boundaries
        assert "Out of scope: UI concerns" in doc.scope_boundaries

    def test_parse_full_document_workflow_steps(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(FULL_AGENTS_MD)
        assert doc.workflow_steps == [
            "Write failing test",
            "Implement feature",
            "Open pull request",
        ]

    def test_parse_full_document_project_context(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(FULL_AGENTS_MD)
        assert "amazing things" in doc.project_context

    def test_parse_raw_content_preserved(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(FULL_AGENTS_MD)
        assert doc.raw_content == FULL_AGENTS_MD

    def test_parse_missing_all_sections(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(MISSING_ALL_SECTIONS_MD)
        assert doc.project_name == "EmptyProject"
        assert doc.capabilities == []
        assert doc.constraints == []
        assert doc.scope_boundaries == []
        assert doc.workflow_steps == []

    def test_parse_no_h1_defaults_project_name(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(NO_H1_MD)
        assert doc.project_name == "Unnamed Project"

    def test_parse_no_h1_still_parses_sections(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(NO_H1_MD)
        assert len(doc.capabilities) == 1
        assert len(doc.constraints) == 1

    def test_parse_extra_sections_captured(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(EXTRA_SECTION_MD)
        assert "Security Policy" in doc.extra_sections
        assert "security team" in doc.extra_sections["Security Policy"]

    def test_parse_alias_scope_heading(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(ALIAS_HEADING_MD)
        assert len(doc.scope_boundaries) == 1
        assert "In scope: the core" in doc.scope_boundaries

    def test_parse_alias_workflow_heading(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(ALIAS_HEADING_MD)
        assert len(doc.workflow_steps) == 1

    def test_parse_mixed_list_types(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(MIXED_LIST_MD)
        assert len(doc.capabilities) == 3
        assert "Bullet cap one" in doc.capabilities
        assert "Bullet cap two" in doc.capabilities
        assert "Bullet cap three" in doc.capabilities

    def test_parse_mixed_numbered_constraints(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(MIXED_LIST_MD)
        assert len(doc.constraints) == 2
        assert "Numbered constraint one" in doc.constraints

    def test_parse_h3_heading_as_extra_section(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(H3_HEADING_MD)
        # H3 "Sub-context" should appear as an extra section
        assert "Sub-context" in doc.extra_sections

    def test_parse_unicode_content(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(UNICODE_MD)
        assert "Ünïcödé Project" == doc.project_name
        assert "Handle UTF-8 input safely" in doc.capabilities
        assert "Preserve encoding" in doc.constraints[0]

    def test_parse_empty_string(self, parser: AgentsMdParser) -> None:
        doc = parser.parse("")
        assert doc.project_name == "Unnamed Project"
        assert doc.capabilities == []

    def test_parse_only_whitespace(self, parser: AgentsMdParser) -> None:
        doc = parser.parse("   \n\n   ")
        assert doc.project_name == "Unnamed Project"

    def test_parse_file_reads_from_disk(
        self, parser: AgentsMdParser, agents_md_file: Path
    ) -> None:
        doc = parser.parse_file(str(agents_md_file))
        assert doc.project_name == "MyProject"

    def test_parse_file_unicode_reads_correctly(
        self, parser: AgentsMdParser, unicode_agents_md_file: Path
    ) -> None:
        doc = parser.parse_file(str(unicode_agents_md_file))
        assert "Ünïcödé" in doc.project_name

    def test_parse_file_missing_raises(self, parser: AgentsMdParser, tmp_path: Path) -> None:
        with pytest.raises(Exception):
            parser.parse_file(str(tmp_path / "nonexistent.md"))

    def test_parse_multiple_h1_uses_first(self, parser: AgentsMdParser) -> None:
        content = "# First\n\n# Second\n\n## Capabilities\n\n- cap\n"
        doc = parser.parse(content)
        assert doc.project_name == "First"

    def test_parse_extra_sections_body_stripped(self, parser: AgentsMdParser) -> None:
        content = textwrap.dedent("""\
            # Proj
            ## Custom Section

            Body line here.
        """)
        doc = parser.parse(content)
        assert "Custom Section" in doc.extra_sections
        assert doc.extra_sections["Custom Section"] == "Body line here."

    def test_parse_no_extra_sections_when_all_known(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(FULL_AGENTS_MD)
        assert doc.extra_sections == {}

    def test_parse_capabilities_count(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(FULL_AGENTS_MD)
        assert len(doc.capabilities) == 3

    def test_parse_minimal_document(self, parser: AgentsMdParser) -> None:
        doc = parser.parse(MINIMAL_AGENTS_MD)
        assert doc.project_name == "TinyProject"
        assert len(doc.capabilities) == 1
        assert len(doc.constraints) == 1
        assert len(doc.scope_boundaries) == 1
        assert len(doc.workflow_steps) == 1


# ---------------------------------------------------------------------------
# AgentsMdValidator tests
# ---------------------------------------------------------------------------


class TestAgentsMdValidator:
    """Tests for AgentsMdValidator.validate."""

    @pytest.fixture()
    def validator(self) -> AgentsMdValidator:
        return AgentsMdValidator()

    def test_valid_full_document(
        self, validator: AgentsMdValidator, full_document: AgentsMdDocument
    ) -> None:
        result = validator.validate(full_document)
        assert result.valid is True

    def test_valid_full_document_no_errors(
        self, validator: AgentsMdValidator, full_document: AgentsMdDocument
    ) -> None:
        result = validator.validate(full_document)
        error_issues = [i for i in result.issues if i.severity == "error"]
        assert len(error_issues) == 0

    def test_empty_document_invalid(
        self, validator: AgentsMdValidator, empty_document: AgentsMdDocument
    ) -> None:
        result = validator.validate(empty_document)
        assert result.valid is False

    def test_empty_document_has_five_errors(
        self, validator: AgentsMdValidator, empty_document: AgentsMdDocument
    ) -> None:
        result = validator.validate(empty_document)
        errors = [i for i in result.issues if i.severity == "error"]
        assert len(errors) == 5

    def test_no_h1_produces_warning(self, validator: AgentsMdValidator) -> None:
        doc = AgentsMdDocument(
            project_name="Unnamed Project",
            project_context="Some context.",
            capabilities=["A cap"],
            constraints=["A con"],
            scope_boundaries=["A boundary"],
            workflow_steps=["A step"],
        )
        result = validator.validate(doc)
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert len(warnings) == 1
        assert "Unnamed Project" in warnings[0].message

    def test_no_h1_warning_has_line_number(self, validator: AgentsMdValidator) -> None:
        doc = AgentsMdDocument(
            project_name="Unnamed Project",
            project_context="ctx",
            capabilities=["cap"],
            constraints=["con"],
            scope_boundaries=["bound"],
            workflow_steps=["step"],
        )
        result = validator.validate(doc)
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert warnings[0].line_number == 1

    def test_missing_project_context_produces_error(
        self, validator: AgentsMdValidator
    ) -> None:
        doc = AgentsMdDocument(
            project_name="TestProject",
            project_context="",
            capabilities=["cap"],
            constraints=["con"],
            scope_boundaries=["bound"],
            workflow_steps=["step"],
        )
        result = validator.validate(doc)
        assert result.valid is False
        error_sections = [i.section for i in result.issues if i.severity == "error"]
        assert AgentsSection.project_context in error_sections

    def test_missing_capabilities_produces_error(
        self, validator: AgentsMdValidator
    ) -> None:
        doc = AgentsMdDocument(
            project_name="TestProject",
            project_context="ctx",
            capabilities=[],
            constraints=["con"],
            scope_boundaries=["bound"],
            workflow_steps=["step"],
        )
        result = validator.validate(doc)
        error_sections = [i.section for i in result.issues if i.severity == "error"]
        assert AgentsSection.capabilities in error_sections

    def test_missing_constraints_produces_error(
        self, validator: AgentsMdValidator
    ) -> None:
        doc = AgentsMdDocument(
            project_name="TestProject",
            project_context="ctx",
            capabilities=["cap"],
            constraints=[],
            scope_boundaries=["bound"],
            workflow_steps=["step"],
        )
        result = validator.validate(doc)
        error_sections = [i.section for i in result.issues if i.severity == "error"]
        assert AgentsSection.constraints in error_sections

    def test_missing_scope_boundaries_produces_error(
        self, validator: AgentsMdValidator
    ) -> None:
        doc = AgentsMdDocument(
            project_name="TestProject",
            project_context="ctx",
            capabilities=["cap"],
            constraints=["con"],
            scope_boundaries=[],
            workflow_steps=["step"],
        )
        result = validator.validate(doc)
        error_sections = [i.section for i in result.issues if i.severity == "error"]
        assert AgentsSection.scope_boundaries in error_sections

    def test_missing_workflow_produces_error(
        self, validator: AgentsMdValidator
    ) -> None:
        doc = AgentsMdDocument(
            project_name="TestProject",
            project_context="ctx",
            capabilities=["cap"],
            constraints=["con"],
            scope_boundaries=["bound"],
            workflow_steps=[],
        )
        result = validator.validate(doc)
        error_sections = [i.section for i in result.issues if i.severity == "error"]
        assert AgentsSection.development_workflow in error_sections

    def test_validation_result_contains_document(
        self, validator: AgentsMdValidator, full_document: AgentsMdDocument
    ) -> None:
        result = validator.validate(full_document)
        assert result.document is full_document

    def test_validation_with_warnings_still_valid(
        self, validator: AgentsMdValidator
    ) -> None:
        doc = AgentsMdDocument(
            project_name="Unnamed Project",
            project_context="ctx",
            capabilities=["cap"],
            constraints=["con"],
            scope_boundaries=["bound"],
            workflow_steps=["step"],
        )
        result = validator.validate(doc)
        assert result.valid is True

    def test_valid_document_with_extras(
        self, validator: AgentsMdValidator, document_with_extras: AgentsMdDocument
    ) -> None:
        result = validator.validate(document_with_extras)
        assert result.valid is True

    def test_issue_message_contains_section_name(
        self, validator: AgentsMdValidator, empty_document: AgentsMdDocument
    ) -> None:
        result = validator.validate(empty_document)
        messages = [i.message for i in result.issues]
        assert any("project_context" in m for m in messages)


# ---------------------------------------------------------------------------
# AgentsMdGenerator tests
# ---------------------------------------------------------------------------


class TestAgentsMdGenerator:
    """Tests for AgentsMdGenerator.generate."""

    @pytest.fixture()
    def generator(self) -> AgentsMdGenerator:
        return AgentsMdGenerator()

    def test_generate_contains_project_name(
        self, generator: AgentsMdGenerator, full_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(full_document)
        assert "# MyProject" in output

    def test_generate_contains_capabilities_section(
        self, generator: AgentsMdGenerator, full_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(full_document)
        assert "## Capabilities" in output

    def test_generate_contains_constraints_section(
        self, generator: AgentsMdGenerator, full_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(full_document)
        assert "## Constraints" in output

    def test_generate_contains_scope_boundaries_section(
        self, generator: AgentsMdGenerator, full_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(full_document)
        assert "## Scope Boundaries" in output

    def test_generate_contains_workflow_section(
        self, generator: AgentsMdGenerator, full_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(full_document)
        assert "## Development Workflow" in output

    def test_generate_capabilities_as_bullets(
        self, generator: AgentsMdGenerator, full_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(full_document)
        for cap in full_document.capabilities:
            assert f"- {cap}" in output

    def test_generate_workflow_steps_as_numbered(
        self, generator: AgentsMdGenerator, full_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(full_document)
        for i, step in enumerate(full_document.workflow_steps, start=1):
            assert f"{i}. {step}" in output

    def test_generate_empty_capabilities_placeholder(
        self, generator: AgentsMdGenerator, empty_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(empty_document)
        assert "_None defined._" in output

    def test_generate_empty_constraints_placeholder(
        self, generator: AgentsMdGenerator, empty_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(empty_document)
        assert "_None defined._" in output

    def test_generate_empty_workflow_placeholder(
        self, generator: AgentsMdGenerator, empty_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(empty_document)
        assert "_No steps defined._" in output

    def test_generate_empty_context_placeholder(
        self, generator: AgentsMdGenerator, empty_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(empty_document)
        assert "_No context provided._" in output

    def test_generate_extra_sections_included(
        self, generator: AgentsMdGenerator, document_with_extras: AgentsMdDocument
    ) -> None:
        output = generator.generate(document_with_extras)
        assert "## Security Policy" in output
        assert "security team" in output

    def test_generate_ends_with_newline(
        self, generator: AgentsMdGenerator, full_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(full_document)
        assert output.endswith("\n")

    def test_generate_is_reparseable(
        self, generator: AgentsMdGenerator, full_document: AgentsMdDocument
    ) -> None:
        """Round-trip: generated markdown can be re-parsed to equivalent doc."""
        output = generator.generate(full_document)
        parser = AgentsMdParser()
        reparsed = parser.parse(output)
        assert reparsed.project_name == full_document.project_name
        assert reparsed.capabilities == full_document.capabilities
        assert reparsed.constraints == full_document.constraints

    def test_generate_context_prose_present(
        self, generator: AgentsMdGenerator, full_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(full_document)
        assert full_document.project_context in output

    def test_generate_project_context_heading(
        self, generator: AgentsMdGenerator, full_document: AgentsMdDocument
    ) -> None:
        output = generator.generate(full_document)
        assert "## Project Context" in output


# ---------------------------------------------------------------------------
# ConfigExporter tests
# ---------------------------------------------------------------------------


class TestConfigExporter:
    """Tests for ConfigExporter.to_yaml and to_json."""

    @pytest.fixture()
    def exporter(self) -> ConfigExporter:
        return ConfigExporter()

    def test_to_json_valid_json(
        self, exporter: ConfigExporter, full_document: AgentsMdDocument
    ) -> None:
        output = exporter.to_json(full_document)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_to_json_contains_project_name(
        self, exporter: ConfigExporter, full_document: AgentsMdDocument
    ) -> None:
        output = exporter.to_json(full_document)
        data = json.loads(output)
        assert data["project_name"] == "MyProject"

    def test_to_json_contains_capabilities(
        self, exporter: ConfigExporter, full_document: AgentsMdDocument
    ) -> None:
        output = exporter.to_json(full_document)
        data = json.loads(output)
        assert isinstance(data["capabilities"], list)
        assert len(data["capabilities"]) > 0

    def test_to_json_contains_constraints(
        self, exporter: ConfigExporter, full_document: AgentsMdDocument
    ) -> None:
        output = exporter.to_json(full_document)
        data = json.loads(output)
        assert isinstance(data["constraints"], list)

    def test_to_json_contains_scope_boundaries(
        self, exporter: ConfigExporter, full_document: AgentsMdDocument
    ) -> None:
        output = exporter.to_json(full_document)
        data = json.loads(output)
        assert "scope_boundaries" in data

    def test_to_json_contains_workflow_steps(
        self, exporter: ConfigExporter, full_document: AgentsMdDocument
    ) -> None:
        output = exporter.to_json(full_document)
        data = json.loads(output)
        assert "workflow_steps" in data

    def test_to_json_contains_extra_sections(
        self, exporter: ConfigExporter, document_with_extras: AgentsMdDocument
    ) -> None:
        output = exporter.to_json(document_with_extras)
        data = json.loads(output)
        assert "Security Policy" in data["extra_sections"]

    def test_to_json_indented(
        self, exporter: ConfigExporter, full_document: AgentsMdDocument
    ) -> None:
        output = exporter.to_json(full_document)
        # Indented JSON contains newlines after opening braces
        assert "\n" in output

    def test_to_yaml_valid_yaml(
        self, exporter: ConfigExporter, full_document: AgentsMdDocument
    ) -> None:
        output = exporter.to_yaml(full_document)
        parsed = yaml.safe_load(output)
        assert isinstance(parsed, dict)

    def test_to_yaml_contains_project_name(
        self, exporter: ConfigExporter, full_document: AgentsMdDocument
    ) -> None:
        output = exporter.to_yaml(full_document)
        data = yaml.safe_load(output)
        assert data["project_name"] == "MyProject"

    def test_to_yaml_contains_capabilities(
        self, exporter: ConfigExporter, full_document: AgentsMdDocument
    ) -> None:
        output = exporter.to_yaml(full_document)
        data = yaml.safe_load(output)
        assert isinstance(data["capabilities"], list)

    def test_to_yaml_unicode_preserved(
        self, exporter: ConfigExporter
    ) -> None:
        doc = AgentsMdDocument(
            project_name="Ünïcödé",
            project_context="Context with 日本語",
            capabilities=["Handle UTF-8"],
            constraints=["Preserve encoding: ™"],
            scope_boundaries=["In scope: everything"],
            workflow_steps=["Test"],
        )
        output = exporter.to_yaml(doc)
        data = yaml.safe_load(output)
        assert data["project_name"] == "Ünïcödé"

    def test_to_json_unicode_not_escaped(
        self, exporter: ConfigExporter
    ) -> None:
        doc = AgentsMdDocument(
            project_name="日本語Project",
            project_context="Unicode context.",
            capabilities=["cap"],
            constraints=["con"],
            scope_boundaries=["bound"],
            workflow_steps=["step"],
        )
        output = exporter.to_json(doc)
        assert "日本語Project" in output

    def test_to_yaml_empty_lists(
        self, exporter: ConfigExporter, empty_document: AgentsMdDocument
    ) -> None:
        output = exporter.to_yaml(empty_document)
        data = yaml.safe_load(output)
        assert data["capabilities"] == []

    def test_to_json_project_context_present(
        self, exporter: ConfigExporter, full_document: AgentsMdDocument
    ) -> None:
        output = exporter.to_json(full_document)
        data = json.loads(output)
        assert "project_context" in data


# ---------------------------------------------------------------------------
# generate_template tests
# ---------------------------------------------------------------------------


class TestGenerateTemplate:
    """Tests for the generate_template function."""

    def test_template_contains_project_name(self) -> None:
        result = generate_template("AwesomeProject")
        assert "AwesomeProject" in result

    def test_template_contains_h1(self) -> None:
        result = generate_template("AwesomeProject")
        assert result.startswith("# AwesomeProject")

    def test_template_contains_all_standard_sections(self) -> None:
        result = generate_template("TestProject")
        assert "## Project Context" in result
        assert "## Capabilities" in result
        assert "## Constraints" in result
        assert "## Scope Boundaries" in result
        assert "## Development Workflow" in result

    def test_template_is_string(self) -> None:
        result = generate_template("AnyProject")
        assert isinstance(result, str)

    def test_template_is_parseable(self) -> None:
        result = generate_template("ParseableProject")
        parser = AgentsMdParser()
        doc = parser.parse(result)
        assert doc.project_name == "ParseableProject"

    def test_template_parseable_has_capabilities(self) -> None:
        result = generate_template("ParseableProject")
        parser = AgentsMdParser()
        doc = parser.parse(result)
        assert len(doc.capabilities) > 0

    def test_template_parseable_has_constraints(self) -> None:
        result = generate_template("ParseableProject")
        parser = AgentsMdParser()
        doc = parser.parse(result)
        assert len(doc.constraints) > 0

    def test_template_parseable_is_valid(self) -> None:
        result = generate_template("ValidProject")
        parser = AgentsMdParser()
        validator = AgentsMdValidator()
        doc = parser.parse(result)
        validation = validator.validate(doc)
        assert validation.valid is True

    def test_template_special_chars_in_name(self) -> None:
        result = generate_template("My-Project_2.0")
        assert "My-Project_2.0" in result

    def test_template_empty_project_name(self) -> None:
        result = generate_template("")
        assert isinstance(result, str)

    @pytest.mark.parametrize("project_name", [
        "Alpha",
        "Beta Project",
        "Gamma-Delta",
        "Project123",
        "AumAI Enterprise",
    ])
    def test_template_various_names(self, project_name: str) -> None:
        result = generate_template(project_name)
        assert project_name in result


# ---------------------------------------------------------------------------
# Models tests
# ---------------------------------------------------------------------------


class TestAgentsMdDocument:
    """Tests for AgentsMdDocument model."""

    def test_create_minimal_document(self) -> None:
        doc = AgentsMdDocument(project_name="TestProject")
        assert doc.project_name == "TestProject"
        assert doc.capabilities == []
        assert doc.constraints == []

    def test_project_name_stripped(self) -> None:
        doc = AgentsMdDocument(project_name="  Spaced  ")
        assert doc.project_name == "Spaced"

    def test_empty_project_name_raises(self) -> None:
        with pytest.raises(Exception):
            AgentsMdDocument(project_name="")

    def test_whitespace_only_project_name_raises(self) -> None:
        with pytest.raises(Exception):
            AgentsMdDocument(project_name="   ")

    def test_default_extra_sections_empty_dict(self) -> None:
        doc = AgentsMdDocument(project_name="Test")
        assert doc.extra_sections == {}

    def test_default_workflow_steps_empty_list(self) -> None:
        doc = AgentsMdDocument(project_name="Test")
        assert doc.workflow_steps == []


class TestValidationIssue:
    """Tests for ValidationIssue model."""

    def test_create_error_issue(self) -> None:
        issue = ValidationIssue(
            section=AgentsSection.capabilities,
            severity="error",
            message="Missing capabilities.",
        )
        assert issue.severity == "error"
        assert issue.section == AgentsSection.capabilities

    def test_create_warning_issue(self) -> None:
        issue = ValidationIssue(
            section=AgentsSection.project_context,
            severity="warning",
            message="Some warning.",
            line_number=5,
        )
        assert issue.line_number == 5

    def test_invalid_severity_raises(self) -> None:
        with pytest.raises(Exception):
            ValidationIssue(
                section=AgentsSection.capabilities,
                severity="critical",
                message="msg",
            )

    def test_valid_severities(self) -> None:
        for severity in ("error", "warning", "info"):
            issue = ValidationIssue(
                section=AgentsSection.constraints,
                severity=severity,
                message="msg",
            )
            assert issue.severity == severity

    def test_line_number_optional(self) -> None:
        issue = ValidationIssue(
            section=AgentsSection.constraints,
            severity="info",
            message="info msg",
        )
        assert issue.line_number is None


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_create_valid_result(self, full_document: AgentsMdDocument) -> None:
        result = ValidationResult(valid=True, issues=[], document=full_document)
        assert result.valid is True

    def test_create_invalid_result(self, empty_document: AgentsMdDocument) -> None:
        issue = ValidationIssue(
            section=AgentsSection.capabilities,
            severity="error",
            message="Missing.",
        )
        result = ValidationResult(valid=False, issues=[issue], document=empty_document)
        assert result.valid is False
        assert len(result.issues) == 1

    def test_default_document_is_none(self) -> None:
        result = ValidationResult(valid=True)
        assert result.document is None


class TestAgentsSection:
    """Tests for AgentsSection enum."""

    def test_all_sections_exist(self) -> None:
        sections = [s.value for s in AgentsSection]
        assert "project_context" in sections
        assert "capabilities" in sections
        assert "constraints" in sections
        assert "scope_boundaries" in sections
        assert "development_workflow" in sections

    def test_section_is_string_enum(self) -> None:
        assert isinstance(AgentsSection.capabilities, str)
        assert AgentsSection.capabilities == "capabilities"


# ---------------------------------------------------------------------------
# Hypothesis-based property tests
# ---------------------------------------------------------------------------


@given(project_name=st.text(min_size=1, max_size=100).filter(lambda s: s.strip()))
@settings(max_examples=50)
def test_generate_template_always_contains_name(project_name: str) -> None:
    """generate_template always embeds the project name."""
    result = generate_template(project_name)
    assert project_name in result


@given(
    caps=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
            min_size=1,
            max_size=50,
        ).filter(lambda s: s.strip()),
        max_size=10,
    ),
    cons=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
            min_size=1,
            max_size=50,
        ).filter(lambda s: s.strip()),
        max_size=10,
    ),
)
@settings(max_examples=30)
def test_generator_roundtrip_lists(caps: list[str], cons: list[str]) -> None:
    """Generator produces parseable output preserving list lengths."""
    doc = AgentsMdDocument(
        project_name="HypothesisProject",
        project_context="context",
        capabilities=caps,
        constraints=cons,
        scope_boundaries=["boundary"],
        workflow_steps=["step"],
    )
    generator = AgentsMdGenerator()
    parser = AgentsMdParser()
    output = generator.generate(doc)
    reparsed = parser.parse(output)
    assert len(reparsed.capabilities) == len(caps)
    assert len(reparsed.constraints) == len(cons)


@given(
    lines=st.lists(
        st.one_of(
            st.just("- bullet item"),
            st.just("* star item"),
            st.just("+ plus item"),
            st.just("1. numbered item"),
            st.just("not a list item"),
        ),
        min_size=0,
        max_size=20,
    )
)
@settings(max_examples=30)
def test_extract_list_items_never_raises(lines: list[str]) -> None:
    """_extract_list_items must never raise for any input."""
    result = _extract_list_items(lines)
    assert isinstance(result, list)


@given(
    lines=st.lists(
        st.text(max_size=80),
        min_size=0,
        max_size=20,
    )
)
@settings(max_examples=30)
def test_extract_prose_never_raises(lines: list[str]) -> None:
    """_extract_prose must never raise for any input."""
    result = _extract_prose(lines)
    assert isinstance(result, str)
