---
name: fix-lint-failures
description: Fix linting and code formatting issues from ESLint, Black, Prettier, Ruff, pre-commit hooks. Use when linting checks fail.
allowed-tools: Read, Edit, Bash, Glob, Grep
---

# Fix Linting and Formatting Issues

Provides domain expertise for fixing linting violations. This skill fixes files only - the main loop handles git operations (commit, push, CI, merge).

## Scope

**This skill DOES:**
- Run auto-fixers (ruff, black, eslint --fix, prettier)
- Manually fix violations that auto-fix can't handle
- Validate fixes by re-running linters

**This skill does NOT do (main loop handles these):**
- ❌ Commit changes
- ❌ Push to remote
- ❌ Wait for CI
- ❌ Merge the PR

## Context
Search `.failure-logs.txt` for linting violations using Grep (don't read entire file).

## Environment Setup
```bash
unset VIRTUAL_ENV  # Clear any inherited venv
uv sync            # Ensure dependencies installed
```

## Process

### 1. Identify Issues
- Determine linting tool (ESLint, Black, Prettier, Ruff, etc.)
- Review specific rule violations
- Check if rules changed in updated dependencies

### 2. Apply Auto-Fixes First

**Python**
```bash
uv run ruff check --fix .
uv run ruff format .
# Or run all pre-commit hooks:
uv run pre-commit run --all-files
```

**JavaScript/TypeScript**
```bash
npm run lint:fix   # or yarn lint:fix
npm run format     # if separate formatter exists
```

### 3. Manual Fixes
If auto-fix doesn't resolve everything:
- Read specific error messages
- Fix violations according to rules
- Verify fixes don't break functionality

**Handling Rule Violations:**
- ✅ **PREFER**: Fix the code to comply with the rule
- ✅ **ACCEPTABLE**: Use inline ignores for legitimate exceptions with justification
- ❌ **AVOID**: Adding rules to project-level ignore configuration

**When to use inline ignores:**
- The violation is intentional and well-justified
- **ALWAYS include a comment** explaining why

**Examples:**
```python
# ✅ GOOD: Inline ignore with justification
from module import heavy_dependency  # noqa: PLC0415 - Lazy import after validation

# ❌ BAD: Adding to pyproject.toml ignore list
[tool.ruff.lint]
ignore = ["PLC0415"]  # Don't do this!
```

```typescript
// ✅ GOOD: Inline disable with justification
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- Third-party API returns any
const data: any = await thirdPartyApi();
```

### 4. Validate
Re-run linters to ensure all issues are resolved:
```bash
uv run ruff check .
uv run pre-commit run --all-files
```

## Safety Rules
- ❌ Don't add rules to project-level ignore configuration
- ❌ Don't add ignores without a clear justification comment
- ❌ Don't make functional changes beyond linting
- ✅ Fix code to comply with rules whenever possible
- ✅ Use auto-fixers first
- ✅ Ensure changes are cosmetic only
