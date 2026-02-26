"""Pydantic models for aumai-agentsmd."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class AgentsSection(str, Enum):
    """Known sections of an AGENTS.md document."""

    project_context = "project_context"
    capabilities = "capabilities"
    constraints = "constraints"
    scope_boundaries = "scope_boundaries"
    development_workflow = "development_workflow"


class AgentsMdDocument(BaseModel):
    """Parsed representation of an AGENTS.md file."""

    project_name: str = Field(description="Name of the project")
    project_context: str = Field(default="", description="Project context section text")
    capabilities: list[str] = Field(
        default_factory=list, description="List of capability statements"
    )
    constraints: list[str] = Field(
        default_factory=list, description="List of constraint statements"
    )
    scope_boundaries: list[str] = Field(
        default_factory=list, description="List of scope boundary statements"
    )
    workflow_steps: list[str] = Field(
        default_factory=list, description="List of development workflow steps"
    )
    raw_content: str = Field(default="", description="Original raw markdown content")
    extra_sections: dict[str, str] = Field(
        default_factory=dict, description="Any additional sections not in the standard schema"
    )

    @field_validator("project_name")
    @classmethod
    def project_name_must_not_be_empty(cls, value: str) -> str:
        """Ensure the project name is not blank."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("project_name must not be empty")
        return stripped


class ValidationIssue(BaseModel):
    """A single validation issue found in an AGENTS.md document."""

    section: AgentsSection = Field(description="Which section the issue belongs to")
    severity: str = Field(description="Severity level: error, warning, or info")
    message: str = Field(description="Human-readable description of the issue")
    line_number: int | None = Field(
        default=None, description="Line number where the issue was detected"
    )

    @field_validator("severity")
    @classmethod
    def severity_must_be_valid(cls, value: str) -> str:
        """Restrict severity to known levels."""
        allowed = {"error", "warning", "info"}
        if value not in allowed:
            raise ValueError(f"severity must be one of {allowed}, got {value!r}")
        return value


class ValidationResult(BaseModel):
    """Outcome of validating an AgentsMdDocument."""

    valid: bool = Field(description="True when no errors are present")
    issues: list[ValidationIssue] = Field(
        default_factory=list, description="All issues found during validation"
    )
    document: AgentsMdDocument | None = Field(
        default=None, description="The parsed document, if available"
    )


__all__ = [
    "AgentsSection",
    "AgentsMdDocument",
    "ValidationIssue",
    "ValidationResult",
]
