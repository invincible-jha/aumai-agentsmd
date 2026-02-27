"""Shared pytest fixtures for aumai-agentsmd tests."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from aumai_agentsmd.models import AgentsMdDocument


# ---------------------------------------------------------------------------
# Raw markdown fixtures
# ---------------------------------------------------------------------------

FULL_AGENTS_MD = textwrap.dedent(
    """\
    # MyProject

    ## Project Context

    This project does amazing things with AI agents.

    ## Capabilities

    - Parse AGENTS.md files
    - Validate document structure
    - Generate normalised markdown

    ## Constraints

    - Must not access external APIs without approval
    - Must not store PII data

    ## Scope Boundaries

    - In scope: core agent logic
    - Out of scope: UI concerns

    ## Development Workflow

    1. Write failing test
    2. Implement feature
    3. Open pull request
    """
)

MINIMAL_AGENTS_MD = textwrap.dedent(
    """\
    # TinyProject

    ## Project Context

    A minimal project.

    ## Capabilities

    - Do something

    ## Constraints

    - Don't do bad things

    ## Scope Boundaries

    - In scope: everything useful

    ## Development Workflow

    1. Just ship it
    """
)

MISSING_ALL_SECTIONS_MD = "# EmptyProject\n"

NO_H1_MD = textwrap.dedent(
    """\
    ## Project Context

    Some context without an H1 heading.

    ## Capabilities

    - A capability

    ## Constraints

    - A constraint

    ## Scope Boundaries

    - A boundary

    ## Development Workflow

    1. A step
    """
)

EXTRA_SECTION_MD = textwrap.dedent(
    """\
    # ProjectWithExtras

    ## Project Context

    Context here.

    ## Capabilities

    - Cap one

    ## Constraints

    - Con one

    ## Scope Boundaries

    - Boundary one

    ## Development Workflow

    1. Step one

    ## Security Policy

    All changes must be reviewed by the security team.
    No unencrypted secrets in source control.
    """
)

ALIAS_HEADING_MD = textwrap.dedent(
    """\
    # AliasProject

    ## Project Context

    Context text.

    ## Capabilities

    - Something

    ## Constraints

    - Nothing bad

    ## Scope

    - In scope: the core

    ## Workflow

    1. Start here
    """
)

MIXED_LIST_MD = textwrap.dedent(
    """\
    # MixedProject

    ## Project Context

    Context prose.

    ## Capabilities

    - Bullet cap one
    * Bullet cap two
    + Bullet cap three

    ## Constraints

    1. Numbered constraint one
    2. Numbered constraint two

    ## Scope Boundaries

    - Scope item

    ## Development Workflow

    1. First step
    2. Second step
    """
)

H3_HEADING_MD = textwrap.dedent(
    """\
    # H3Project

    ## Project Context

    High-level context.

    ### Sub-context

    Nested context detail.

    ## Capabilities

    - Cap one

    ## Constraints

    - Con one

    ## Scope Boundaries

    - Boundary

    ## Development Workflow

    1. Step
    """
)

UNICODE_MD = textwrap.dedent(
    """\
    # Ünïcödé Project

    ## Project Context

    Context with special chars: — " " … ñ 你好.

    ## Capabilities

    - Handle UTF-8 input safely

    ## Constraints

    - Preserve encoding: ™ © ®

    ## Scope Boundaries

    - In scope: 日本語 support

    ## Development Workflow

    1. Test unicode paths
    """
)


# ---------------------------------------------------------------------------
# Document fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def full_document() -> AgentsMdDocument:
    """A fully-populated AgentsMdDocument with all standard sections."""
    return AgentsMdDocument(
        project_name="MyProject",
        project_context="This project does amazing things with AI agents.",
        capabilities=["Parse AGENTS.md files", "Validate document structure"],
        constraints=["Must not access external APIs without approval"],
        scope_boundaries=["In scope: core agent logic", "Out of scope: UI concerns"],
        workflow_steps=["Write failing test", "Implement feature", "Open pull request"],
        raw_content=FULL_AGENTS_MD,
        extra_sections={},
    )


@pytest.fixture()
def empty_document() -> AgentsMdDocument:
    """An AgentsMdDocument that is fully empty (no list items, no prose)."""
    return AgentsMdDocument(
        project_name="EmptyProject",
        project_context="",
        capabilities=[],
        constraints=[],
        scope_boundaries=[],
        workflow_steps=[],
        raw_content="# EmptyProject\n",
        extra_sections={},
    )


@pytest.fixture()
def document_with_extras() -> AgentsMdDocument:
    """AgentsMdDocument carrying extra_sections content."""
    return AgentsMdDocument(
        project_name="ProjectWithExtras",
        project_context="Context here.",
        capabilities=["Cap one"],
        constraints=["Con one"],
        scope_boundaries=["Boundary one"],
        workflow_steps=["Step one"],
        raw_content=EXTRA_SECTION_MD,
        extra_sections={
            "Security Policy": (
                "All changes must be reviewed by the security team.\n"
                "No unencrypted secrets in source control."
            )
        },
    )


# ---------------------------------------------------------------------------
# File-system fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def agents_md_file(tmp_path: Path) -> Path:
    """Write the full AGENTS.md content to a temporary file and return its path."""
    file_path = tmp_path / "AGENTS.md"
    file_path.write_text(FULL_AGENTS_MD, encoding="utf-8")
    return file_path


@pytest.fixture()
def minimal_agents_md_file(tmp_path: Path) -> Path:
    """Write the minimal AGENTS.md content to a temporary file."""
    file_path = tmp_path / "AGENTS.md"
    file_path.write_text(MINIMAL_AGENTS_MD, encoding="utf-8")
    return file_path


@pytest.fixture()
def empty_agents_md_file(tmp_path: Path) -> Path:
    """Write a near-empty AGENTS.md to a temporary file."""
    file_path = tmp_path / "AGENTS.md"
    file_path.write_text(MISSING_ALL_SECTIONS_MD, encoding="utf-8")
    return file_path


@pytest.fixture()
def unicode_agents_md_file(tmp_path: Path) -> Path:
    """Write a unicode AGENTS.md to a temporary file."""
    file_path = tmp_path / "AGENTS.md"
    file_path.write_text(UNICODE_MD, encoding="utf-8")
    return file_path
