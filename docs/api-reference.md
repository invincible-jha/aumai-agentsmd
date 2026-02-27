# API Reference — aumai-agentsmd

Complete reference for all public classes, functions, and Pydantic models.

All symbols are importable directly from the top-level package:

```python
from aumai_agentsmd import (
    AgentsMdParser,
    AgentsMdValidator,
    AgentsMdGenerator,
    ConfigExporter,
    generate_template,
    AgentsMdDocument,
    AgentsSection,
    ValidationIssue,
    ValidationResult,
)
```

---

## Models (`aumai_agentsmd.models`)

### `AgentsSection`

```python
class AgentsSection(str, Enum):
    project_context = "project_context"
    capabilities = "capabilities"
    constraints = "constraints"
    scope_boundaries = "scope_boundaries"
    development_workflow = "development_workflow"
```

Enumeration of the five canonical sections of an AGENTS.md document. Used in `ValidationIssue.section` to identify which section a validation issue belongs to.

Being a `str` enum, values can be compared directly with strings:

```python
from aumai_agentsmd import AgentsSection

section = AgentsSection.capabilities
print(section == "capabilities")   # True
print(section.value)               # "capabilities"
```

---

### `AgentsMdDocument`

```python
class AgentsMdDocument(BaseModel):
    project_name: str
    project_context: str = ""
    capabilities: list[str] = []
    constraints: list[str] = []
    scope_boundaries: list[str] = []
    workflow_steps: list[str] = []
    raw_content: str = ""
    extra_sections: dict[str, str] = {}
```

The parsed, in-memory representation of an AGENTS.md file. All fields are validated by Pydantic at construction time.

#### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `project_name` | `str` | required | The H1 heading text. Must not be empty (validated). |
| `project_context` | `str` | `""` | Prose text from the `## Project Context` section. |
| `capabilities` | `list[str]` | `[]` | Bullet/numbered list items from `## Capabilities`. |
| `constraints` | `list[str]` | `[]` | Bullet/numbered list items from `## Constraints`. |
| `scope_boundaries` | `list[str]` | `[]` | Bullet/numbered list items from `## Scope Boundaries` or `## Scope`. |
| `workflow_steps` | `list[str]` | `[]` | Bullet/numbered list items from `## Development Workflow` or `## Workflow`. |
| `raw_content` | `str` | `""` | The original, unmodified Markdown string as read from disk. |
| `extra_sections` | `dict[str, str]` | `{}` | Heading text → body text for all unrecognised headings. |

#### Validators

`project_name` is stripped of surrounding whitespace and must not be blank. Constructing an `AgentsMdDocument` with `project_name=""` or `project_name="   "` raises `pydantic.ValidationError`.

#### Example

```python
from aumai_agentsmd import AgentsMdDocument

doc = AgentsMdDocument(
    project_name="My Agent",
    project_context="Handles order fulfilment queries.",
    capabilities=["Read order records", "Send email confirmations"],
    constraints=["Must not modify order status directly"],
    scope_boundaries=["In scope: read-only order queries"],
    workflow_steps=["Receive query", "Look up order", "Respond"],
)

print(doc.project_name)     # "My Agent"
print(doc.capabilities[0])  # "Read order records"

# Serialise to dict
data = doc.model_dump()
```

---

### `ValidationIssue`

```python
class ValidationIssue(BaseModel):
    section: AgentsSection
    severity: str
    message: str
    line_number: int | None = None
```

Describes a single problem found during validation.

#### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `section` | `AgentsSection` | required | Which section the issue belongs to. |
| `severity` | `str` | required | Severity level. Must be one of: `"error"`, `"warning"`, `"info"`. |
| `message` | `str` | required | Human-readable description of the problem. |
| `line_number` | `int \| None` | `None` | Line number in the source file where the issue was detected, if known. |

#### Validators

`severity` is validated against the set `{"error", "warning", "info"}`. Passing any other value raises `pydantic.ValidationError`.

#### Example

```python
from aumai_agentsmd import ValidationIssue, AgentsSection

issue = ValidationIssue(
    section=AgentsSection.capabilities,
    severity="error",
    message="Required section 'capabilities' is missing or empty.",
    line_number=None,
)

print(issue.severity)   # "error"
print(issue.section.value)  # "capabilities"
```

---

### `ValidationResult`

```python
class ValidationResult(BaseModel):
    valid: bool
    issues: list[ValidationIssue] = []
    document: AgentsMdDocument | None = None
```

The outcome of running `AgentsMdValidator.validate()`.

#### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `valid` | `bool` | required | `True` when no `error`-severity issues were found. Warnings do not affect this flag. |
| `issues` | `list[ValidationIssue]` | `[]` | All issues found. May include warnings and info-level issues even when `valid` is `True`. |
| `document` | `AgentsMdDocument \| None` | `None` | The parsed document that was validated. |

#### Example

```python
from aumai_agentsmd import AgentsMdParser, AgentsMdValidator

parser = AgentsMdParser()
validator = AgentsMdValidator()

doc = parser.parse_file("AGENTS.md")
result = validator.validate(doc)

print(result.valid)         # True or False
print(len(result.issues))   # Number of issues found

for issue in result.issues:
    print(f"[{issue.severity}] {issue.message}")
```

---

## Core Classes (`aumai_agentsmd.core`)

### `AgentsMdParser`

```python
class AgentsMdParser:
    def parse(self, content: str) -> AgentsMdDocument: ...
    def parse_file(self, path: str) -> AgentsMdDocument: ...
```

Converts raw AGENTS.md Markdown into a structured `AgentsMdDocument`. No constructor arguments are required.

---

#### `AgentsMdParser.parse(content)`

Parse a Markdown string and return a structured document.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `content` | `str` | The raw Markdown text of an AGENTS.md file. |

**Returns:** `AgentsMdDocument`

**Behaviour:**
- The first H1 heading (`# Title`) becomes `project_name`. If no H1 is present, `project_name` defaults to `"Unnamed Project"`.
- Subsequent headings are looked up in the heading alias map. Recognised headings set the current section; unrecognised headings go to `extra_sections`.
- Bullet items (`-`, `*`, `+`) and numbered list items (`1.`) under list sections are extracted as individual strings.
- The `Project Context` section is extracted as a single prose string (non-list, non-heading lines joined with spaces).
- The original `content` string is stored verbatim in `raw_content`.

**Example:**

```python
from aumai_agentsmd import AgentsMdParser

parser = AgentsMdParser()
doc = parser.parse("# My Agent\n\n## Capabilities\n\n- Do thing A\n- Do thing B\n")
print(doc.project_name)    # "My Agent"
print(doc.capabilities)    # ["Do thing A", "Do thing B"]
```

---

#### `AgentsMdParser.parse_file(path)`

Read a file from disk and parse it.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `path` | `str` | Filesystem path to the AGENTS.md file. Must be readable. |

**Returns:** `AgentsMdDocument`

**Raises:**
- `FileNotFoundError` — if `path` does not exist.
- `PermissionError` — if the file cannot be read.
- `UnicodeDecodeError` — if the file is not valid UTF-8.

**Example:**

```python
from aumai_agentsmd import AgentsMdParser

parser = AgentsMdParser()
doc = parser.parse_file("/workspace/myproject/AGENTS.md")
```

---

### `AgentsMdValidator`

```python
class AgentsMdValidator:
    def validate(self, doc: AgentsMdDocument) -> ValidationResult: ...
```

Validates that an `AgentsMdDocument` contains all required sections. No constructor arguments are required.

---

#### `AgentsMdValidator.validate(doc)`

Check a document for required sections and return a `ValidationResult`.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `doc` | `AgentsMdDocument` | The parsed document to validate. |

**Returns:** `ValidationResult`

**Validation rules:**
- `project_context` must be a non-empty string → `error` if missing.
- `capabilities` must be a non-empty list → `error` if empty.
- `constraints` must be a non-empty list → `error` if empty.
- `scope_boundaries` must be a non-empty list → `error` if empty.
- `workflow_steps` (`development_workflow` section) must be a non-empty list → `error` if empty.
- `project_name` must not be `"Unnamed Project"` → `warning` at line 1 if defaulted.

The `valid` field on the result is `True` only when no `error`-severity issues exist. Warnings do not affect `valid`.

**Example:**

```python
from aumai_agentsmd import AgentsMdParser, AgentsMdValidator

parser = AgentsMdParser()
validator = AgentsMdValidator()

doc = parser.parse_file("AGENTS.md")
result = validator.validate(doc)

if not result.valid:
    for issue in result.issues:
        if issue.severity == "error":
            print(f"MISSING: {issue.section.value}")
```

---

### `AgentsMdGenerator`

```python
class AgentsMdGenerator:
    def generate(self, doc: AgentsMdDocument) -> str: ...
```

Renders an `AgentsMdDocument` back to canonical AGENTS.md Markdown. No constructor arguments are required.

---

#### `AgentsMdGenerator.generate(doc)`

Return a Markdown string for `doc`.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `doc` | `AgentsMdDocument` | The document to render. |

**Returns:** `str` — a complete, canonically formatted AGENTS.md Markdown string.

**Output format:**
- H1 heading for `project_name`.
- H2 headings for all five standard sections.
- `project_context` output as a prose block (or `_No context provided._` if empty).
- `capabilities`, `constraints`, `scope_boundaries` as `- item` bullet lists.
- `workflow_steps` as `1.`, `2.` numbered lists.
- `extra_sections` each output as an H2 heading followed by the body text.

**Example:**

```python
from aumai_agentsmd import AgentsMdDocument, AgentsMdGenerator

doc = AgentsMdDocument(
    project_name="My Agent",
    project_context="Handles order queries.",
    capabilities=["Read orders", "Send confirmations"],
    constraints=["No PII storage"],
    scope_boundaries=["In scope: orders only"],
    workflow_steps=["Validate input", "Query API", "Respond"],
)

generator = AgentsMdGenerator()
markdown = generator.generate(doc)
# Returns a complete, formatted AGENTS.md string
```

---

### `ConfigExporter`

```python
class ConfigExporter:
    def to_json(self, doc: AgentsMdDocument) -> str: ...
    def to_yaml(self, doc: AgentsMdDocument) -> str: ...
```

Serialises an `AgentsMdDocument` to JSON or YAML. No constructor arguments are required. The `raw_content` field is excluded from both output formats.

---

#### `ConfigExporter.to_json(doc)`

Return a pretty-printed JSON string for `doc`.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `doc` | `AgentsMdDocument` | The document to serialise. |

**Returns:** `str` — a JSON string with 2-space indentation.

**Exported fields:** `project_name`, `project_context`, `capabilities`, `constraints`, `scope_boundaries`, `workflow_steps`, `extra_sections`. (`raw_content` is excluded.)

**Example:**

```python
from aumai_agentsmd import AgentsMdParser, ConfigExporter
import json

parser = AgentsMdParser()
exporter = ConfigExporter()

doc = parser.parse_file("AGENTS.md")
json_str = exporter.to_json(doc)
data = json.loads(json_str)
print(data["capabilities"])
```

---

#### `ConfigExporter.to_yaml(doc)`

Return a YAML string for `doc`.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `doc` | `AgentsMdDocument` | The document to serialise. |

**Returns:** `str` — a YAML string using block style (no flow-style abbreviation), preserving insertion order.

**Example:**

```python
from aumai_agentsmd import AgentsMdParser, ConfigExporter

parser = AgentsMdParser()
exporter = ConfigExporter()

doc = parser.parse_file("AGENTS.md")
yaml_str = exporter.to_yaml(doc)
print(yaml_str)
```

---

## Module-Level Functions

### `generate_template(project_name)`

```python
def generate_template(project_name: str) -> str: ...
```

Return a filled AGENTS.md template string for a new project.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `project_name` | `str` | The project name to embed in the H1 heading of the template. |

**Returns:** `str` — a complete AGENTS.md template string with placeholder content for all five sections.

**Example:**

```python
from aumai_agentsmd import generate_template

template = generate_template("Inventory Sync Agent")
with open("AGENTS.md", "w", encoding="utf-8") as f:
    f.write(template)
```

**Template content (abbreviated):**

```markdown
# Inventory Sync Agent

## Project Context

Describe the project purpose and goals here.

## Capabilities

- Capability one
- Capability two
...
```

---

## Package Version

```python
import aumai_agentsmd
print(aumai_agentsmd.__version__)  # "0.1.0"
```

---

## Complete Import Map

```python
# Models
from aumai_agentsmd import AgentsSection        # Enum of canonical section names
from aumai_agentsmd import AgentsMdDocument     # Parsed document model
from aumai_agentsmd import ValidationIssue      # Single validation issue
from aumai_agentsmd import ValidationResult     # Outcome of validate()

# Core classes
from aumai_agentsmd import AgentsMdParser       # Markdown -> AgentsMdDocument
from aumai_agentsmd import AgentsMdValidator    # AgentsMdDocument -> ValidationResult
from aumai_agentsmd import AgentsMdGenerator    # AgentsMdDocument -> Markdown string
from aumai_agentsmd import ConfigExporter       # AgentsMdDocument -> JSON / YAML

# Functions
from aumai_agentsmd import generate_template    # project_name -> template Markdown string
```
