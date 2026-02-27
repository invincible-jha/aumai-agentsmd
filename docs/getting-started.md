# Getting Started with aumai-agentsmd

This guide takes you from a fresh Python environment to a working AGENTS.md workflow in about 15 minutes.

---

## Prerequisites

- Python 3.11 or later
- `pip` (comes with Python)
- A terminal

Verify your Python version:

```bash
python --version
# Python 3.11.x or later
```

---

## Installation

### From PyPI (recommended)

```bash
pip install aumai-agentsmd
```

Verify the install:

```bash
aumai-agentsmd --version
# aumai-agentsmd, version 0.1.0
```

### From source

```bash
git clone https://github.com/aumai/aumai-agentsmd.git
cd aumai-agentsmd
pip install .
```

### Development mode (editable install with test dependencies)

```bash
git clone https://github.com/aumai/aumai-agentsmd.git
cd aumai-agentsmd
pip install -e ".[dev]"
```

This installs the package in editable mode so changes to `src/` take effect immediately without reinstalling.

---

## Your First AGENTS.md

### Step 1 — Scaffold a template

```bash
aumai-agentsmd init --project-name "Support Triage Agent"
```

This creates `AGENTS.md` in the current directory with placeholder content:

```markdown
# Support Triage Agent

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
```

### Step 2 — Edit the file

Open `AGENTS.md` in your editor and replace the placeholders. A realistic example for a support triage agent:

```markdown
# Support Triage Agent

## Project Context

Automates first-level triage of customer support tickets. Reads from
the helpdesk queue, classifies tickets by urgency and category, and
routes them to the appropriate team inbox.

## Capabilities

- Read open tickets from the helpdesk API
- Classify tickets by urgency (P1–P4) and category
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
- Out of scope: SLA breach escalation (handled by a separate agent)

## Development Workflow

1. Write a failing test for the new behaviour
2. Implement the change in src/
3. Run ruff and mypy to pass lint and type checks
4. Open a pull request against main
5. Request review from at least one team member
6. Squash-merge after approval
```

### Step 3 — Validate

```bash
aumai-agentsmd validate AGENTS.md
# AGENTS.md is valid: AGENTS.md
```

If any section is missing, the validator tells you exactly what to fix:

```
[ERROR] capabilities: Required section 'capabilities' is missing or empty.
Validation failed.
```

### Step 4 — Export to JSON

```bash
aumai-agentsmd parse AGENTS.md --output json
```

This prints a structured JSON object you can pipe into other tools, store in a database, or pass to an agent runtime:

```json
{
  "project_name": "Support Triage Agent",
  "project_context": "Automates first-level triage of customer support tickets...",
  "capabilities": [
    "Read open tickets from the helpdesk API",
    "Classify tickets by urgency (P1-P4) and category",
    ...
  ],
  "constraints": [...],
  "scope_boundaries": [...],
  "workflow_steps": [...],
  "extra_sections": {}
}
```

---

## Common Patterns

### Pattern 1 — Validate in CI

Add this step to your GitHub Actions workflow to fail the build if AGENTS.md is incomplete:

```yaml
- name: Validate AGENTS.md
  run: |
    pip install aumai-agentsmd
    aumai-agentsmd validate AGENTS.md
```

The command exits with code `1` on any validation error, which fails the CI step automatically.

---

### Pattern 2 — Export for agent runtime configuration

Many agent frameworks accept a dict or JSON file at startup to define capabilities and constraints. Use the Python API to feed the parsed document directly:

```python
import json
from aumai_agentsmd import AgentsMdParser, ConfigExporter

parser = AgentsMdParser()
exporter = ConfigExporter()

doc = parser.parse_file("AGENTS.md")
config_json = exporter.to_json(doc)

# Pass to your agent framework
agent_config = json.loads(config_json)
agent = MyAgentFramework(
    capabilities=agent_config["capabilities"],
    constraints=agent_config["constraints"],
)
```

---

### Pattern 3 — Programmatic document construction and round-trip

When you generate agent configs from code (for example, from a database of agent definitions), build an `AgentsMdDocument` directly and render it to Markdown:

```python
from aumai_agentsmd import AgentsMdDocument, AgentsMdGenerator, AgentsMdValidator

doc = AgentsMdDocument(
    project_name="Inventory Sync Agent",
    project_context="Synchronises product inventory between the ERP and the e-commerce platform.",
    capabilities=[
        "Read inventory levels from ERP",
        "Write inventory updates to e-commerce platform",
        "Log sync events to audit trail",
    ],
    constraints=[
        "Must not delete product records",
        "Must not modify pricing data",
        "Must not exceed 1000 API calls per hour",
    ],
    scope_boundaries=[
        "In scope: inventory quantity synchronisation",
        "Out of scope: order processing",
        "Out of scope: pricing or promotions",
    ],
    workflow_steps=[
        "Run nightly at 02:00 UTC",
        "Read delta from ERP since last sync",
        "Push updates to e-commerce API",
        "Write sync summary to audit log",
    ],
)

# Validate before writing
validator = AgentsMdValidator()
result = validator.validate(doc)
if not result.valid:
    raise ValueError("Document validation failed")

# Render to Markdown
generator = AgentsMdGenerator()
markdown = generator.generate(doc)
with open("AGENTS.md", "w", encoding="utf-8") as f:
    f.write(markdown)
```

---

### Pattern 4 — Normalise an existing file

If you have AGENTS.md files with inconsistent formatting (varying heading levels, mixed bullet styles), normalise them all with the `generate` command:

```bash
# Dry-run: preview normalised output
aumai-agentsmd generate AGENTS.md

# Write normalised output back to the file
aumai-agentsmd generate AGENTS.md --output AGENTS.md

# Normalise every AGENTS.md in a monorepo
find . -name "AGENTS.md" -exec aumai-agentsmd generate {} --output {} \;
```

---

### Pattern 5 — Access extra sections in code

When teams add project-specific sections beyond the standard five, they are preserved in `extra_sections`:

```markdown
## Security Contact

security@example.com — response within 24 hours.

## Runbook

See https://wiki.example.com/agents/support-triage
```

```python
from aumai_agentsmd import AgentsMdParser

parser = AgentsMdParser()
doc = parser.parse_file("AGENTS.md")

security_contact = doc.extra_sections.get("Security Contact", "")
runbook_url = doc.extra_sections.get("Runbook", "")
print(security_contact)  # "security@example.com — response within 24 hours."
```

---

## Troubleshooting FAQ

**Q: `aumai-agentsmd: command not found`**

The CLI entry point is not on your `PATH`. This usually means the package's bin directory is not in your shell's `PATH`. Try:

```bash
python -m aumai_agentsmd.cli --help
```

Or ensure your Python scripts directory is on `PATH` (e.g. `~/.local/bin` on Linux/macOS).

---

**Q: Validation passes but my capabilities list is empty**

The parser only recognises bullet lists (`-`, `*`, `+`) and numbered lists (`1.`, `2.`) as list items. Plain prose under a `## Capabilities` heading will be stored in `project_context` logic, not in the list. Ensure each capability starts with `- ` or a number.

---

**Q: My custom section heading is not showing up in `capabilities`**

Only the five canonical section names (and their aliases) are mapped to structured fields. All other headings go into `extra_sections`. If you need a heading to map to a structured field, use one of the canonical names listed in the README.

---

**Q: `parse_file` raises `FileNotFoundError`**

The path argument must point to an existing file. The CLI (`validate`, `parse`, `generate`) enforces this with `type=click.Path(exists=True)`. In Python, pass an absolute path or ensure the working directory is correct.

---

**Q: Can I parse a file that is missing some sections?**

Yes. The parser never raises an exception on missing sections — it simply leaves the corresponding field empty. The `validate()` step is what reports missing sections as errors. You can parse and use a partial document without validating it.

---

**Q: The `generate` command changes my file. Is that expected?**

Yes. `generate` normalises the output: it enforces H2 headings for all standard sections, `-` bullets for list items, and numbered steps for the workflow. The semantic content is preserved; only formatting is changed.

---

## Next Steps

- Read the [API Reference](api-reference.md) for complete class and method documentation
- See the [examples/quickstart.py](../examples/quickstart.py) for runnable demo code
- Integrate with [aumai-policycompiler](https://github.com/aumai/aumai-policycompiler) to compile constraints into runtime enforcement rules
