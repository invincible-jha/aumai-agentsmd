"""Quickstart examples for aumai-agentsmd.

Demonstrates the four main use cases:
  1. Scaffolding a template AGENTS.md
  2. Parsing a Markdown string into a structured document
  3. Validating a document and inspecting issues
  4. Exporting a parsed document to JSON and YAML

Run this file directly to see all demos:

    python examples/quickstart.py
"""

from __future__ import annotations

import json

from aumai_agentsmd import (
    AgentsMdDocument,
    AgentsMdGenerator,
    AgentsMdParser,
    AgentsMdValidator,
    ConfigExporter,
    generate_template,
)

# ---------------------------------------------------------------------------
# Sample AGENTS.md content used throughout the demos
# ---------------------------------------------------------------------------

SAMPLE_AGENTS_MD = """
# Support Triage Agent

## Project Context

Automates first-level triage of customer support tickets. Reads from
the helpdesk queue, classifies tickets by urgency and category, and
routes them to the appropriate team inbox.

## Capabilities

- Read open tickets from the helpdesk API
- Classify tickets by urgency (P1-P4) and category
- Route classified tickets to team queues
- Post a one-line classification summary as a ticket note

## Constraints

- Must not reply directly to customers
- Must not access billing or payment records
- Must not modify ticket history or timestamps
- Must not store raw ticket text outside the processing pipeline

## Scope Boundaries

- In scope: ticket classification and routing logic
- In scope: helpdesk API read and write access
- Out of scope: direct customer communication
- Out of scope: billing system integration

## Development Workflow

1. Write a failing test for the new behaviour
2. Implement the change in src/
3. Run ruff and mypy to pass lint and type checks
4. Open a pull request against main
5. Squash-merge after approval

## Security Contact

security@example.com — response within 24 hours.
"""


def demo_template_generation() -> None:
    """Demo 1: Generate a template AGENTS.md for a new project.

    generate_template() returns a ready-to-edit string with placeholder
    content for all five required sections.
    """
    print("=" * 60)
    print("DEMO 1 — Template generation")
    print("=" * 60)

    template = generate_template("My New Agent")

    # Show the first few lines
    first_lines = template.splitlines()[:10]
    for line in first_lines:
        print(line)
    print("... (truncated)")
    print()


def demo_parse_and_inspect() -> None:
    """Demo 2: Parse a Markdown string and inspect each field.

    AgentsMdParser.parse() converts raw Markdown into a typed
    AgentsMdDocument Pydantic model. All fields are strongly typed.
    """
    print("=" * 60)
    print("DEMO 2 — Parsing and inspection")
    print("=" * 60)

    parser = AgentsMdParser()
    doc = parser.parse(SAMPLE_AGENTS_MD)

    print(f"Project name    : {doc.project_name}")
    print(f"Context         : {doc.project_context[:60]}...")
    print(f"Capabilities    : {len(doc.capabilities)} items")
    for cap in doc.capabilities:
        print(f"  - {cap}")
    print(f"Constraints     : {len(doc.constraints)} items")
    print(f"Scope boundaries: {len(doc.scope_boundaries)} items")
    print(f"Workflow steps  : {len(doc.workflow_steps)} items")

    # Extra (non-standard) sections are preserved verbatim
    print(f"Extra sections  : {list(doc.extra_sections.keys())}")
    security_contact = doc.extra_sections.get("Security Contact", "(not set)")
    print(f"  Security Contact: {security_contact.strip()}")
    print()


def demo_validation() -> None:
    """Demo 3: Validate a document and inspect the result.

    AgentsMdValidator.validate() checks for required sections.
    This demo shows both a passing validation and a failing one.
    """
    print("=" * 60)
    print("DEMO 3 — Validation")
    print("=" * 60)

    parser = AgentsMdParser()
    validator = AgentsMdValidator()

    # --- Case A: valid document ---
    doc_valid = parser.parse(SAMPLE_AGENTS_MD)
    result_valid = validator.validate(doc_valid)
    print(f"Case A (complete document) — valid: {result_valid.valid}")
    if result_valid.issues:
        for issue in result_valid.issues:
            print(f"  [{issue.severity.upper()}] {issue.section.value}: {issue.message}")
    else:
        print("  No issues found.")

    # --- Case B: document with missing sections ---
    incomplete_markdown = """
# Incomplete Agent

## Project Context

This agent is missing most sections.
"""
    doc_incomplete = parser.parse(incomplete_markdown)
    result_incomplete = validator.validate(doc_incomplete)
    print(f"\nCase B (incomplete document) — valid: {result_incomplete.valid}")
    for issue in result_incomplete.issues:
        location = f" (line {issue.line_number})" if issue.line_number else ""
        print(f"  [{issue.severity.upper()}] {issue.section.value}{location}: {issue.message}")
    print()


def demo_export_and_generate() -> None:
    """Demo 4: Export to JSON/YAML and regenerate normalised Markdown.

    ConfigExporter converts the parsed document to JSON or YAML.
    AgentsMdGenerator round-trips it back to canonical Markdown.
    """
    print("=" * 60)
    print("DEMO 4 — Export and generation")
    print("=" * 60)

    parser = AgentsMdParser()
    exporter = ConfigExporter()
    generator = AgentsMdGenerator()

    doc = parser.parse(SAMPLE_AGENTS_MD)

    # Export to JSON
    json_string = exporter.to_json(doc)
    parsed_json = json.loads(json_string)
    print("JSON export (capabilities field):")
    print(json.dumps(parsed_json["capabilities"], indent=2))

    # Export to YAML (show first few lines)
    yaml_string = exporter.to_yaml(doc)
    yaml_preview = yaml_string.splitlines()[:8]
    print("\nYAML export (first 8 lines):")
    for line in yaml_preview:
        print(line)
    print("...")

    # Round-trip back to Markdown
    regenerated = generator.generate(doc)
    regenerated_preview = regenerated.splitlines()[:12]
    print("\nRegenerated Markdown (first 12 lines):")
    for line in regenerated_preview:
        print(line)
    print("...")
    print()


def demo_programmatic_construction() -> None:
    """Demo 5: Build an AgentsMdDocument in code without parsing.

    When agent configs are generated programmatically (from a database,
    a form, or another config file), construct the document directly
    and render it to Markdown using AgentsMdGenerator.
    """
    print("=" * 60)
    print("DEMO 5 — Programmatic construction")
    print("=" * 60)

    # Build the document from pure Python — no Markdown parsing needed
    doc = AgentsMdDocument(
        project_name="Inventory Sync Agent",
        project_context=(
            "Synchronises product inventory between the ERP system and "
            "the e-commerce storefront on a nightly schedule."
        ),
        capabilities=[
            "Read inventory levels from ERP REST API",
            "Write inventory updates to e-commerce platform API",
            "Log sync events to the audit trail",
        ],
        constraints=[
            "Must not delete product records",
            "Must not modify pricing or promotion data",
            "Must not exceed 1000 API calls per hour",
        ],
        scope_boundaries=[
            "In scope: inventory quantity synchronisation",
            "Out of scope: order processing",
            "Out of scope: pricing or promotions",
        ],
        workflow_steps=[
            "Run nightly at 02:00 UTC",
            "Read inventory delta from ERP since last sync timestamp",
            "Push updates to e-commerce API",
            "Write sync summary to audit log",
        ],
    )

    # Validate before writing
    validator = AgentsMdValidator()
    result = validator.validate(doc)
    print(f"Validation: valid={result.valid}, issues={len(result.issues)}")

    # Render to Markdown
    generator = AgentsMdGenerator()
    markdown = generator.generate(doc)
    print("\nGenerated AGENTS.md:")
    print(markdown)


def main() -> None:
    """Run all demos in sequence."""
    demo_template_generation()
    demo_parse_and_inspect()
    demo_validation()
    demo_export_and_generate()
    demo_programmatic_construction()

    print("All demos complete.")


if __name__ == "__main__":
    main()
