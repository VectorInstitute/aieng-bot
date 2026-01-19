---
name: fix-test-failures
description: Fix test assertion failures, timeouts, and test suite failures from dependency updates. Use when Jest, pytest, unittest, or other test checks fail.
allowed-tools: Read, Edit, Bash, Glob, Grep
---

# Fix Test Failures

Provides domain expertise for fixing test failures. This skill fixes files only - the main loop handles git operations (commit, push, CI, merge).

## Scope

**This skill DOES:**
- Analyze test failure logs to identify root cause
- Fix test code for API/dependency changes
- Update test fixtures, mocks, and assertions
- Validate fixes by running tests locally

**This skill does NOT do (main loop handles these):**
- ❌ Commit changes
- ❌ Push to remote
- ❌ Wait for CI
- ❌ Merge the PR

## Context
Search `.failure-logs.txt` for test errors using Grep (don't read entire file).

## Environment Setup
```bash
unset VIRTUAL_ENV  # Clear any inherited venv
uv sync            # Ensure dependencies installed
```

## Process

### 1. Analyze Failures
- Search test failure logs to identify what's broken
- Examine dependency changes that caused the failure
- Check for breaking API changes in updated packages

### 2. Fix Strategy by Test Type

**Backend Tests (pytest, unittest)**
- Update for API changes in dependencies
- Fix test fixtures for changed data structures
- Adjust import paths if package structure changed
- Update assertions for new behavior

**Frontend Tests (Jest, React Testing Library)**
- Update component APIs changed by dependencies
- Fix test mocks for updated library interfaces
- Adjust snapshots if UI changes are valid
- Update test configuration if framework changed

**Integration Tests**
- Check if API contracts changed
- Update test data for new schemas
- Fix timing issues from async behavior changes

### 3. Implementation
- Make minimal, targeted changes only
- Preserve original test intent
- Follow existing code patterns
- Don't skip tests or add ignore comments

### 4. Validate
Run the test suite to verify fixes work:
```bash
uv run pytest                    # Python
npm test                         # JavaScript
```

## Safety Rules
- ❌ Don't skip tests without understanding failures
- ❌ Don't make unrelated changes
- ❌ Don't update other dependencies unnecessarily
- ✅ Ensure fixes are valid and test the right behavior
- ✅ Preserve original test intent
