"""CLI entry point for aumai-agentsmd."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from aumai_agentsmd.core import (
    AgentsMdGenerator,
    AgentsMdParser,
    AgentsMdValidator,
    ConfigExporter,
    generate_template,
)
from aumai_agentsmd.models import ValidationIssue


@click.group()
@click.version_option()
def main() -> None:
    """AumAI Agentsmd CLI — parse, validate, and generate AGENTS.md files."""


@main.command("validate")
@click.argument("agents_md_path", metavar="AGENTS_MD", type=click.Path(exists=True))
def validate_command(agents_md_path: str) -> None:
    """Validate the structure of an AGENTS.md file.

    Exits with code 1 when errors are found.
    """
    parser = AgentsMdParser()
    validator = AgentsMdValidator()

    try:
        doc = parser.parse_file(agents_md_path)
    except Exception as exc:
        click.echo(f"Error reading file: {exc}", err=True)
        sys.exit(1)

    result = validator.validate(doc)

    if not result.issues:
        click.echo(f"AGENTS.md is valid: {agents_md_path}")
        return

    severity_colour: dict[str, str] = {
        "error": "red",
        "warning": "yellow",
        "info": "blue",
    }
    for issue in result.issues:
        colour = severity_colour.get(issue.severity, "white")
        location = _format_location(issue)
        click.echo(
            click.style(f"[{issue.severity.upper()}]", fg=colour)
            + f" {issue.section.value}{location}: {issue.message}"
        )

    if result.valid:
        click.echo(click.style("Validation passed with warnings.", fg="yellow"))
    else:
        click.echo(click.style("Validation failed.", fg="red"))
        sys.exit(1)


def _format_location(issue: ValidationIssue) -> str:
    """Return a line-number suffix string or empty string."""
    if issue.line_number is not None:
        return f" (line {issue.line_number})"
    return ""


@main.command("parse")
@click.argument("agents_md_path", metavar="AGENTS_MD", type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "yaml"], case_sensitive=False),
    default="json",
    show_default=True,
    help="Output format.",
)
def parse_command(agents_md_path: str, output: str) -> None:
    """Parse AGENTS.md and print the configuration as JSON or YAML."""
    parser = AgentsMdParser()
    exporter = ConfigExporter()

    try:
        doc = parser.parse_file(agents_md_path)
    except Exception as exc:
        click.echo(f"Error reading file: {exc}", err=True)
        sys.exit(1)

    if output.lower() == "yaml":
        click.echo(exporter.to_yaml(doc))
    else:
        click.echo(exporter.to_json(doc))


@main.command("init")
@click.option(
    "--project-name",
    default="MyProject",
    show_default=True,
    help="Name of the project to embed in the template.",
)
@click.option(
    "--output",
    "-o",
    default="AGENTS.md",
    show_default=True,
    help="Destination file path.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite the output file if it already exists.",
)
def init_command(project_name: str, output: str, force: bool) -> None:
    """Generate a template AGENTS.md for a new project."""
    destination = Path(output)
    if destination.exists() and not force:
        click.echo(
            f"File already exists: {output}. Use --force to overwrite.",
            err=True,
        )
        sys.exit(1)

    content = generate_template(project_name)
    destination.write_text(content, encoding="utf-8")
    click.echo(f"Created {output} for project '{project_name}'.")


@main.command("generate")
@click.argument("agents_md_path", metavar="AGENTS_MD", type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    default=None,
    help="Write output to this file instead of stdout.",
)
def generate_command(agents_md_path: str, output: str | None) -> None:
    """Round-trip parse an AGENTS.md and re-emit it as normalised markdown."""
    parser = AgentsMdParser()
    generator = AgentsMdGenerator()

    try:
        doc = parser.parse_file(agents_md_path)
    except Exception as exc:
        click.echo(f"Error reading file: {exc}", err=True)
        sys.exit(1)

    rendered = generator.generate(doc)
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
        click.echo(f"Written to {output}")
    else:
        click.echo(rendered)


if __name__ == "__main__":
    main()
