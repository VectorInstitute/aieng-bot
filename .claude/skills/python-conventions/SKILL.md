---
name: python-conventions
description: Python tooling conventions for this organization. Use when working with Python projects, fixing linting issues, or managing dependencies.
---

# Python Conventions

## Package Management

Use `uv` exclusively:

```bash
uv sync          # Install dependencies
uv lock          # Regenerate lock file
uv add "pkg"     # Add dependency
uv run <cmd>     # Run in project environment
```

**Lock files**: Never manually edit. Delete and regenerate:
```bash
rm uv.lock && uv lock
```

## Linting

**Tools** (in order):
1. `ruff check --fix` - Linting
2. `ruff format` - Formatting
3. `mypy` - Type checking

**Run all**: `uv run pre-commit run --all-files`

## Inline Ignores

Always include justification:
```python
from module import thing  # noqa: PLC0415 - Lazy import after validation
```

## Environment

Clear inherited environments:
```bash
unset VIRTUAL_ENV
uv sync
```
