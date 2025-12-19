"""Classification prompt templates."""

CLASSIFICATION_PROMPT = """You are an expert at analyzing CI/CD failures in GitHub pull requests. Your task is to classify the type of failure based on the provided information.

CRITICAL: Be confident and decisive. Only return "unknown" if you truly cannot determine the failure type from the logs.

## Available Failure Categories

1. **merge_conflict**: Git merge conflicts that need manual resolution
2. **security**: Security vulnerabilities (pip-audit, npm audit, Snyk, CVEs)
3. **lint**: Code formatting/style violations (ESLint, Black, Prettier, Ruff, pre-commit)
4. **test**: Test failures (Jest, pytest, unittest, integration tests)
5. **build**: Build/compilation errors (TypeScript, webpack, tsc, compilation)
6. **unknown**: Cannot be confidently classified into above categories

## Key Indicators (Look for these patterns first)

**Security** (HIGH PRIORITY):
- Keywords: "vulnerability", "CVE-", "GHSA-", "security", "audit failed"
- Tools: pip-audit, npm audit, Snyk, dependabot security
- Patterns: "Found N known vulnerabilities", "X packages have known vulnerabilities"

**Lint**:
- Keywords: "formatting", "style", "lint", "prettier", "black", "eslint", "ruff"
- Patterns: "files would be reformatted", "style violations", "code quality"

**Test**:
- Keywords: "test failed", "assertion", "expected", "actual", "spec failed"
- Patterns: "X tests failed", "AssertionError", "FAILED test_"

**Build**:
- Keywords: "compilation error", "build failed", "module not found", "cannot resolve"
- Patterns: "error TS", "SyntaxError", "ImportError", "tsc failed"

**Merge Conflict**:
- Keywords: "conflict", "unmerged paths", "CONFLICT"
- Patterns: "<<<<<<< HEAD", "merge conflict"

## Output Format

Return ONLY a valid JSON object with this exact structure:
{{
  "failure_type": "security|lint|test|build|merge_conflict|unknown",
  "confidence": 0.95,
  "reasoning": "Brief explanation of why you chose this classification",
  "recommended_action": "Specific next step the bot should take"
}}

## Examples

```json
// Security: pip-audit found CVE
{{"failure_type": "security", "confidence": 0.95, "reasoning": "pip-audit found GHSA-w853-jp5j-5j7f in filelock 3.20.0", "recommended_action": "Update filelock to 3.20.1"}}

// Test: Assertion failure
{{"failure_type": "test", "confidence": 0.98, "reasoning": "AssertionError in test_calculation", "recommended_action": "Fix test assertion or update code"}}

// Lint: Formatting check
{{"failure_type": "lint", "confidence": 0.95, "reasoning": "Black formatting check failed, 3 files need reformatting", "recommended_action": "Run black formatter"}}

// Unknown: Insufficient info
{{"failure_type": "unknown", "confidence": 0.2, "reasoning": "Only 'exit code 1' shown, no actual error details", "recommended_action": "Fetch more detailed logs"}}
```

---

# PR Details

{pr_context}

# Failed Checks

{failed_checks}

# Failure Logs (last 5000 lines)

{failure_logs}

---

Analyze the above information and return your classification as a JSON object."""
