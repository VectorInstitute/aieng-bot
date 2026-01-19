---
name: fix-security-audit
description: Fix security vulnerabilities from pip-audit, npm audit, Snyk, and other security scanners. Use when security audit checks fail with CVE warnings.
allowed-tools: Read, Edit, Bash, Glob, Grep, WebSearch
---

# Fix Security Vulnerabilities

Provides domain expertise for fixing security vulnerabilities. This skill fixes files only - the main loop handles git operations (commit, push, CI, merge).

## Scope

**This skill DOES:**
- Analyze vulnerability reports to identify CVEs
- Update packages to patched versions
- Validate fixes by re-running security audit

**This skill does NOT do (main loop handles these):**
- ❌ Commit changes
- ❌ Push to remote
- ❌ Wait for CI
- ❌ Merge the PR

## Context
Search `.failure-logs.txt` for CVE numbers and vulnerability reports using Grep (don't read entire file).

## Environment Setup
```bash
unset VIRTUAL_ENV  # Clear any inherited venv
uv sync            # Install dependencies
```

## Process

### 1. Analyze Vulnerabilities
- Search for vulnerable packages and CVE numbers
- Determine severity (Critical, High, Medium, Low)
- Note the fixed versions mentioned in the logs

### 2. Detect Package Manager
```bash
# Check for uv (Python - modern)
ls uv.lock pyproject.toml 2>/dev/null

# Check for npm (JavaScript)
ls package.json package-lock.json 2>/dev/null
```

### 3. Fix by Package Manager

**For uv repos (preferred for Vector Institute)**
```bash
# Update vulnerable package to fixed version
uv add "package_name>=FIXED_VERSION"

# Sync environment
uv sync
```

**For npm repos**
```bash
npm audit fix  # Try automatic fixes first

# If automatic fix doesn't work:
npm install package@fixed-version
```

### 4. Severity-Based Decisions

**Critical/High**: MUST fix immediately
- Update to patched version
- If no patch exists, research workarounds (use WebSearch)

**Medium/Low**: Fix whenever possible
- Only consider ignoring if vulnerability is not exploitable in this context

### 5. Validate
Re-run security audit to verify fixes:
```bash
uv run pip-audit              # Python
npm audit                     # JavaScript
```

## Safety Rules
- ❌ NEVER use `ignore-vulns` or similar flags to bypass checks
- ❌ NEVER ignore vulnerabilities without investigation
- ❌ NEVER downgrade packages
- ✅ ALWAYS attempt to update to patched version first
- ✅ ALWAYS re-run audit to verify fix worked
- ✅ Use WebSearch to research CVE details if needed
