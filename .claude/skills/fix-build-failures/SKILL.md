---
name: fix-build-failures
description: Fix build and compilation errors from TypeScript, webpack, Vite, Python builds. Use when build/compile checks fail.
allowed-tools: Read, Edit, Bash, Glob, Grep
---

# Fix Build and Compilation Failures

Provides domain expertise for fixing build failures. This skill fixes files only - the main loop handles git operations (commit, push, CI, merge).

## Scope

**This skill DOES:**
- Analyze build error logs to identify root cause
- Fix compilation errors (TypeScript, Python, etc.)
- Update build configuration files
- Validate fixes by running build locally

**This skill does NOT do (main loop handles these):**
- ❌ Commit changes
- ❌ Push to remote
- ❌ Wait for CI
- ❌ Merge the PR

## Context
Search `.failure-logs.txt` for build errors using Grep (don't read entire file).

## Environment Setup
```bash
unset VIRTUAL_ENV  # Clear any inherited venv
uv sync            # Install dependencies
```

## Process

### 1. Identify Failure Type
- TypeScript compilation errors
- Webpack/Vite/build tool errors
- Python build errors
- Docker build failures

### 2. Fix by Type

**TypeScript Compilation**
- Update type annotations for new definitions
- Fix method calls with new signatures
- Replace deprecated APIs

**Build Tool Errors (Webpack/Vite)**
- Update build configuration
- Fix incompatible plugins
- Resolve module import issues

**Python Build**
- Update import statements
- Add missing dependencies to requirements
- Resolve version conflicts

**Docker Build**
- Update base images
- Pin specific versions
- Fix package installation commands

### 3. Implementation Steps
- Reproduce build locally if possible
- Identify root cause from error messages
- Check package changelogs for breaking changes
- Apply targeted fixes

### 4. Validate
```bash
# Python
uv run python -m build

# Node.js
npm ci && npm run build

# Docker
docker build -t test .
```

## Safety Rules
- ❌ Don't add `@ts-ignore` or `type: ignore` to bypass errors
- ❌ Don't loosen TypeScript strictness
- ❌ Don't remove type checking
- ✅ Understand and fix root cause
- ✅ Follow migration guides from packages
