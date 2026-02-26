"""Core logic for aumai-agentsmd: parsing, validation, generation, and export."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

import yaml

from aumai_agentsmd.models import (
    AgentsMdDocument,
    AgentsSection,
    ValidationIssue,
    ValidationResult,
)

# Mapping from heading text variants (lowercased) to canonical section keys.
_HEADING_MAP: Final[dict[str, str]] = {
    "project context": "project_context",
    "capabilities": "capabilities",
    "constraints": "constraints",
    "scope boundaries": "scope_boundaries",
    "scope": "scope_boundaries",
    "development workflow": "development_workflow",
    "workflow": "development_workflow",
}

# Heading levels to recognise (H1–H3).
_HEADING_RE: Final[re.Pattern[str]] = re.compile(r"^(#{1,3})\s+(.+)$")

# Bullet-list item pattern.
_BULLET_RE: Final[re.Pattern[str]] = re.compile(r"^[\-\*\+]\s+(.+)$")

# Numbered list item pattern.
_NUMBERED_RE: Final[re.Pattern[str]] = re.compile(r"^\d+\.\s+(.+)$")


def _extract_list_items(lines: list[str]) -> list[str]:
    """Return non-empty text from bullet or numbered list lines."""
    items: list[str] = []
    for line in lines:
        bullet_match = _BULLET_RE.match(line.strip())
        numbered_match = _NUMBERED_RE.match(line.strip())
        if bullet_match:
            items.append(bullet_match.group(1).strip())
        elif numbered_match:
            items.append(numbered_match.group(1).strip())
    return items


def _extract_prose(lines: list[str]) -> str:
    """Return non-list, non-heading lines joined as a prose block."""
    prose_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _HEADING_RE.match(stripped):
            continue
        if _BULLET_RE.match(stripped) or _NUMBERED_RE.match(stripped):
            continue
        prose_lines.append(stripped)
    return " ".join(prose_lines)


class AgentsMdParser:
    """Parse AGENTS.md markdown text into an AgentsMdDocument."""

    def parse(self, content: str) -> AgentsMdDocument:
        """Parse markdown *content* string and return a structured document.

        The first H1 heading is used as the project name.  Subsequent headings
        determine section assignment.  Unknown headings are stored in
        ``extra_sections``.
        """
        lines = content.splitlines()
        project_name: str = ""
        sections: dict[str, list[str]] = {}
        current_section: str | None = None
        extra_sections: dict[str, str] = {}
        extra_lines: dict[str, list[str]] = {}

        for line in lines:
            heading_match = _HEADING_RE.match(line.strip())
            if heading_match:
                level = len(heading_match.group(1))
                heading_text = heading_match.group(2).strip()
                # First H1 becomes the project name.
                if level == 1 and not project_name:
                    project_name = heading_text
                    current_section = None
                    continue
                canonical = _HEADING_MAP.get(heading_text.lower())
                if canonical:
                    current_section = canonical
                    if canonical not in sections:
                        sections[canonical] = []
                else:
                    current_section = f"_extra:{heading_text}"
                    extra_lines[heading_text] = []
            else:
                if current_section is not None:
                    if current_section.startswith("_extra:"):
                        key = current_section[len("_extra:"):]
                        extra_lines.setdefault(key, []).append(line)
                    else:
                        sections.setdefault(current_section, []).append(line)

        # Build extra_sections from accumulated lines.
        for heading, body_lines in extra_lines.items():
            extra_sections[heading] = "\n".join(body_lines).strip()

        workflow_lines = sections.get("development_workflow", [])

        return AgentsMdDocument(
            project_name=project_name or "Unnamed Project",
            project_context=_extract_prose(sections.get("project_context", [])),
            capabilities=_extract_list_items(sections.get("capabilities", [])),
            constraints=_extract_list_items(sections.get("constraints", [])),
            scope_boundaries=_extract_list_items(sections.get("scope_boundaries", [])),
            workflow_steps=_extract_list_items(workflow_lines),
            raw_content=content,
            extra_sections=extra_sections,
        )

    def parse_file(self, path: str) -> AgentsMdDocument:
        """Read *path* from disk and delegate to :meth:`parse`."""
        content = Path(path).read_text(encoding="utf-8")
        return self.parse(content)


_VALIDATOR_REQUIRED: Final[list[tuple[AgentsSection, str]]] = [
    (AgentsSection.project_context, "project_context"),
    (AgentsSection.capabilities, "capabilities"),
    (AgentsSection.constraints, "constraints"),
    (AgentsSection.scope_boundaries, "scope_boundaries"),
    (AgentsSection.development_workflow, "development_workflow"),
]


class AgentsMdValidator:
    """Validate an AgentsMdDocument for required sections and content."""

    def validate(self, doc: AgentsMdDocument) -> ValidationResult:
        """Return a ValidationResult describing all issues found in *doc*."""
        issues: list[ValidationIssue] = []

        field_values: dict[str, str | list[str]] = {
            "project_context": doc.project_context,
            "capabilities": doc.capabilities,
            "constraints": doc.constraints,
            "scope_boundaries": doc.scope_boundaries,
            "development_workflow": doc.workflow_steps,
        }

        for section_enum, field_name in _VALIDATOR_REQUIRED:
            value = field_values[field_name]
            # project_context is a str; others are lists.
            is_empty = not value if isinstance(value, str) else len(value) == 0
            if is_empty:
                issues.append(
                    ValidationIssue(
                        section=section_enum,
                        severity="error",
                        message=f"Required section '{section_enum.value}' is missing or empty.",
                        line_number=None,
                    )
                )

        if not doc.project_name or doc.project_name == "Unnamed Project":
            issues.append(
                ValidationIssue(
                    section=AgentsSection.project_context,
                    severity="warning",
                    message="No H1 project name found; defaulted to 'Unnamed Project'.",
                    line_number=1,
                )
            )

        has_errors = any(i.severity == "error" for i in issues)
        return ValidationResult(
            valid=not has_errors,
            issues=issues,
            document=doc,
        )


class AgentsMdGenerator:
    """Render an AgentsMdDocument back to AGENTS.md markdown."""

    def generate(self, doc: AgentsMdDocument) -> str:
        """Return a markdown string representing *doc*."""
        lines: list[str] = [
            f"# {doc.project_name}",
            "",
            "## Project Context",
            "",
            doc.project_context or "_No context provided._",
            "",
            "## Capabilities",
            "",
        ]
        for cap in doc.capabilities:
            lines.append(f"- {cap}")
        if not doc.capabilities:
            lines.append("_None defined._")
        lines.extend(["", "## Constraints", ""])
        for con in doc.constraints:
            lines.append(f"- {con}")
        if not doc.constraints:
            lines.append("_None defined._")
        lines.extend(["", "## Scope Boundaries", ""])
        for boundary in doc.scope_boundaries:
            lines.append(f"- {boundary}")
        if not doc.scope_boundaries:
            lines.append("_None defined._")
        lines.extend(["", "## Development Workflow", ""])
        for i, step in enumerate(doc.workflow_steps, start=1):
            lines.append(f"{i}. {step}")
        if not doc.workflow_steps:
            lines.append("_No steps defined._")
        for heading, body in doc.extra_sections.items():
            lines.extend(["", f"## {heading}", "", body])
        lines.append("")
        return "\n".join(lines)


_TEMPLATE: Final[str] = """\
# {project_name}

## Project Context

Describe the project purpose and goals here.

## Capabilities

- Capability one
- Capability two
- Capability three

## Constraints

- Must not access external APIs without explicit approval
- Must not store PII data
- Must not exceed defined resource budgets

## Scope Boundaries

- In scope: core agent logic and tool integrations
- Out of scope: UI and frontend concerns
- Out of scope: data pipeline infrastructure

## Development Workflow

1. Write failing test
2. Implement feature
3. Run linter and type checker
4. Open pull request for review
5. Squash-merge after approval
"""


class ConfigExporter:
    """Export AgentsMdDocument to YAML or JSON configuration formats."""

    def _to_dict(self, doc: AgentsMdDocument) -> dict[str, object]:
        """Convert document to a plain dict suitable for serialisation."""
        return {
            "project_name": doc.project_name,
            "project_context": doc.project_context,
            "capabilities": doc.capabilities,
            "constraints": doc.constraints,
            "scope_boundaries": doc.scope_boundaries,
            "workflow_steps": doc.workflow_steps,
            "extra_sections": doc.extra_sections,
        }

    def to_yaml(self, doc: AgentsMdDocument) -> str:
        """Return YAML string for *doc*."""
        data = self._to_dict(doc)
        return str(yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False))

    def to_json(self, doc: AgentsMdDocument) -> str:
        """Return pretty-printed JSON string for *doc*."""
        data = self._to_dict(doc)
        return json.dumps(data, indent=2, ensure_ascii=False)


def generate_template(project_name: str) -> str:
    """Return a filled AGENTS.md template for *project_name*."""
    return _TEMPLATE.format(project_name=project_name)


__all__ = [
    "AgentsMdParser",
    "AgentsMdValidator",
    "AgentsMdGenerator",
    "ConfigExporter",
    "generate_template",
]
