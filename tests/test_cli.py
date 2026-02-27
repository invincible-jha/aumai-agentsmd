"""Comprehensive CLI tests for aumai-agentsmd."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from aumai_agentsmd.cli import main, _format_location
from aumai_agentsmd.models import AgentsSection, ValidationIssue

from conftest import FULL_AGENTS_MD, MINIMAL_AGENTS_MD, MISSING_ALL_SECTIONS_MD


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def valid_agents_file(tmp_path: Path) -> Path:
    path = tmp_path / "AGENTS.md"
    path.write_text(FULL_AGENTS_MD, encoding="utf-8")
    return path


@pytest.fixture()
def invalid_agents_file(tmp_path: Path) -> Path:
    path = tmp_path / "AGENTS.md"
    path.write_text(MISSING_ALL_SECTIONS_MD, encoding="utf-8")
    return path


@pytest.fixture()
def minimal_agents_file(tmp_path: Path) -> Path:
    path = tmp_path / "AGENTS.md"
    path.write_text(MINIMAL_AGENTS_MD, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# main group tests
# ---------------------------------------------------------------------------


class TestMainGroup:
    """Tests for the top-level CLI group."""

    def test_version_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "validate" in result.output
        assert "parse" in result.output
        assert "init" in result.output
        assert "generate" in result.output

    def test_no_args_shows_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, [])
        # Click groups return exit code 0 for --help but 0 or 2 with no args
        assert result.exit_code in (0, 2)


# ---------------------------------------------------------------------------
# validate command tests
# ---------------------------------------------------------------------------


class TestValidateCommand:
    """Tests for the 'validate' CLI command."""

    def test_validate_valid_file_exit_zero(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["validate", str(valid_agents_file)])
        assert result.exit_code == 0

    def test_validate_valid_file_reports_valid(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["validate", str(valid_agents_file)])
        assert "valid" in result.output.lower()

    def test_validate_invalid_file_exit_one(
        self, runner: CliRunner, invalid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["validate", str(invalid_agents_file)])
        assert result.exit_code == 1

    def test_validate_invalid_file_reports_error(
        self, runner: CliRunner, invalid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["validate", str(invalid_agents_file)])
        assert "ERROR" in result.output or "failed" in result.output.lower()

    def test_validate_missing_file_exit_nonzero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nonexistent.md"
        result = runner.invoke(main, ["validate", str(missing)])
        assert result.exit_code != 0

    def test_validate_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["validate", "--help"])
        assert result.exit_code == 0
        assert "AGENTS_MD" in result.output

    def test_validate_with_warnings_exit_zero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """A file with warnings only should exit 0 (still valid)."""
        from conftest import NO_H1_MD
        path = tmp_path / "AGENTS.md"
        path.write_text(NO_H1_MD, encoding="utf-8")
        result = runner.invoke(main, ["validate", str(path)])
        assert result.exit_code == 0

    def test_validate_warning_shows_warning_text(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        from conftest import NO_H1_MD
        path = tmp_path / "AGENTS.md"
        path.write_text(NO_H1_MD, encoding="utf-8")
        result = runner.invoke(main, ["validate", str(path)])
        assert "WARNING" in result.output

    def test_validate_minimal_file_exit_zero(
        self, runner: CliRunner, minimal_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["validate", str(minimal_agents_file)])
        assert result.exit_code == 0

    def test_validate_output_contains_section_name(
        self, runner: CliRunner, invalid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["validate", str(invalid_agents_file)])
        # Should mention at least one section name
        assert any(
            sec in result.output
            for sec in [
                "project_context",
                "capabilities",
                "constraints",
                "scope_boundaries",
                "development_workflow",
            ]
        )

    def test_validate_passed_with_warnings_message(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        from conftest import NO_H1_MD
        path = tmp_path / "AGENTS.md"
        path.write_text(NO_H1_MD, encoding="utf-8")
        result = runner.invoke(main, ["validate", str(path)])
        assert "warnings" in result.output.lower() or "WARNING" in result.output


# ---------------------------------------------------------------------------
# parse command tests
# ---------------------------------------------------------------------------


class TestParseCommand:
    """Tests for the 'parse' CLI command."""

    def test_parse_default_json_output(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["parse", str(valid_agents_file)])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, dict)

    def test_parse_json_contains_project_name(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["parse", str(valid_agents_file)])
        data = json.loads(result.output)
        assert data["project_name"] == "MyProject"

    def test_parse_json_contains_capabilities(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["parse", str(valid_agents_file)])
        data = json.loads(result.output)
        assert isinstance(data["capabilities"], list)
        assert len(data["capabilities"]) > 0

    def test_parse_explicit_json_flag(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["parse", str(valid_agents_file), "--output", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "project_name" in data

    def test_parse_yaml_output(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["parse", str(valid_agents_file), "--output", "yaml"])
        assert result.exit_code == 0
        data = yaml.safe_load(result.output)
        assert isinstance(data, dict)

    def test_parse_yaml_contains_project_name(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["parse", str(valid_agents_file), "--output", "yaml"])
        data = yaml.safe_load(result.output)
        assert data["project_name"] == "MyProject"

    def test_parse_yaml_short_flag(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["parse", str(valid_agents_file), "-o", "yaml"])
        assert result.exit_code == 0
        data = yaml.safe_load(result.output)
        assert "project_name" in data

    def test_parse_missing_file_exit_nonzero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nonexistent.md"
        result = runner.invoke(main, ["parse", str(missing)])
        assert result.exit_code != 0

    def test_parse_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["parse", "--help"])
        assert result.exit_code == 0
        assert "json" in result.output.lower()
        assert "yaml" in result.output.lower()

    def test_parse_json_constraints_list(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["parse", str(valid_agents_file)])
        data = json.loads(result.output)
        assert isinstance(data["constraints"], list)

    def test_parse_json_workflow_steps(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["parse", str(valid_agents_file)])
        data = json.loads(result.output)
        assert isinstance(data["workflow_steps"], list)
        assert len(data["workflow_steps"]) == 3

    def test_parse_yaml_case_insensitive(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["parse", str(valid_agents_file), "--output", "YAML"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# init command tests
# ---------------------------------------------------------------------------


class TestInitCommand:
    """Tests for the 'init' CLI command."""

    def test_init_creates_default_file(self, runner: CliRunner) -> None:
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0
            assert Path("AGENTS.md").exists()

    def test_init_default_project_name(self, runner: CliRunner) -> None:
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["init"])
            content = Path("AGENTS.md").read_text(encoding="utf-8")
            assert "MyProject" in content

    def test_init_custom_project_name(self, runner: CliRunner) -> None:
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["init", "--project-name", "AwesomeProject"])
            assert result.exit_code == 0
            content = Path("AGENTS.md").read_text(encoding="utf-8")
            assert "AwesomeProject" in content

    def test_init_custom_output_path(self, runner: CliRunner) -> None:
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["init", "--output", "MY_AGENTS.md"])
            assert result.exit_code == 0
            assert Path("MY_AGENTS.md").exists()

    def test_init_short_output_flag(self, runner: CliRunner) -> None:
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["init", "-o", "OUTPUT.md"])
            assert result.exit_code == 0
            assert Path("OUTPUT.md").exists()

    def test_init_existing_file_without_force_fails(self, runner: CliRunner) -> None:
        with runner.isolated_filesystem():
            Path("AGENTS.md").write_text("existing content", encoding="utf-8")
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 1

    def test_init_existing_file_without_force_error_message(
        self, runner: CliRunner
    ) -> None:
        with runner.isolated_filesystem():
            Path("AGENTS.md").write_text("existing content", encoding="utf-8")
            result = runner.invoke(main, ["init"])
            assert "already exists" in result.output or "already exists" in (result.stderr or "")

    def test_init_force_overwrites_existing(self, runner: CliRunner) -> None:
        with runner.isolated_filesystem():
            Path("AGENTS.md").write_text("old content", encoding="utf-8")
            result = runner.invoke(main, ["init", "--force"])
            assert result.exit_code == 0
            content = Path("AGENTS.md").read_text(encoding="utf-8")
            assert "MyProject" in content
            assert "old content" not in content

    def test_init_output_mentions_project_name(self, runner: CliRunner) -> None:
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["init", "--project-name", "TestProject"])
            assert "TestProject" in result.output

    def test_init_file_is_valid_agents_md(self, runner: CliRunner) -> None:
        from aumai_agentsmd.core import AgentsMdParser, AgentsMdValidator
        with runner.isolated_filesystem():
            runner.invoke(main, ["init", "--project-name", "ValidProject"])
            content = Path("AGENTS.md").read_text(encoding="utf-8")
            parser = AgentsMdParser()
            validator = AgentsMdValidator()
            doc = parser.parse(content)
            result = validator.validate(doc)
            assert result.valid is True

    def test_init_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["init", "--help"])
        assert result.exit_code == 0
        assert "project-name" in result.output or "project_name" in result.output

    def test_init_success_message_contains_filename(self, runner: CliRunner) -> None:
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["init", "-o", "MY_AGENTS.md"])
            assert "MY_AGENTS.md" in result.output


# ---------------------------------------------------------------------------
# generate command tests
# ---------------------------------------------------------------------------


class TestGenerateCommand:
    """Tests for the 'generate' CLI command."""

    def test_generate_stdout_output(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["generate", str(valid_agents_file)])
        assert result.exit_code == 0
        assert "# MyProject" in result.output

    def test_generate_contains_all_sections(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["generate", str(valid_agents_file)])
        assert "## Project Context" in result.output
        assert "## Capabilities" in result.output
        assert "## Constraints" in result.output
        assert "## Scope Boundaries" in result.output
        assert "## Development Workflow" in result.output

    def test_generate_to_file(
        self, runner: CliRunner, valid_agents_file: Path, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "output.md"
        result = runner.invoke(
            main, ["generate", str(valid_agents_file), "--output", str(output_path)]
        )
        assert result.exit_code == 0
        assert output_path.exists()

    def test_generate_file_output_contains_project_name(
        self, runner: CliRunner, valid_agents_file: Path, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "output.md"
        runner.invoke(
            main, ["generate", str(valid_agents_file), "--output", str(output_path)]
        )
        content = output_path.read_text(encoding="utf-8")
        assert "MyProject" in content

    def test_generate_short_output_flag(
        self, runner: CliRunner, valid_agents_file: Path, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "output.md"
        result = runner.invoke(
            main, ["generate", str(valid_agents_file), "-o", str(output_path)]
        )
        assert result.exit_code == 0

    def test_generate_missing_file_exit_nonzero(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nonexistent.md"
        result = runner.invoke(main, ["generate", str(missing)])
        assert result.exit_code != 0

    def test_generate_to_file_confirms_written(
        self, runner: CliRunner, valid_agents_file: Path, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "output.md"
        result = runner.invoke(
            main, ["generate", str(valid_agents_file), "--output", str(output_path)]
        )
        assert "Written to" in result.output or str(output_path) in result.output

    def test_generate_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["generate", "--help"])
        assert result.exit_code == 0
        assert "AGENTS_MD" in result.output

    def test_generate_output_is_valid_markdown(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["generate", str(valid_agents_file)])
        output = result.output
        assert output.startswith("#")

    def test_generate_capabilities_in_output(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["generate", str(valid_agents_file)])
        assert "Parse AGENTS.md files" in result.output

    def test_generate_numbered_workflow_in_output(
        self, runner: CliRunner, valid_agents_file: Path
    ) -> None:
        result = runner.invoke(main, ["generate", str(valid_agents_file)])
        assert "1. Write failing test" in result.output


# ---------------------------------------------------------------------------
# _format_location helper tests
# ---------------------------------------------------------------------------


class TestFormatLocation:
    """Tests for the _format_location helper function."""

    def test_with_line_number(self) -> None:
        issue = ValidationIssue(
            section=AgentsSection.capabilities,
            severity="error",
            message="msg",
            line_number=10,
        )
        result = _format_location(issue)
        assert "(line 10)" in result

    def test_without_line_number(self) -> None:
        issue = ValidationIssue(
            section=AgentsSection.capabilities,
            severity="error",
            message="msg",
            line_number=None,
        )
        result = _format_location(issue)
        assert result == ""

    def test_line_number_one(self) -> None:
        issue = ValidationIssue(
            section=AgentsSection.constraints,
            severity="warning",
            message="msg",
            line_number=1,
        )
        result = _format_location(issue)
        assert "(line 1)" in result

    def test_large_line_number(self) -> None:
        issue = ValidationIssue(
            section=AgentsSection.constraints,
            severity="info",
            message="msg",
            line_number=9999,
        )
        result = _format_location(issue)
        assert "9999" in result
