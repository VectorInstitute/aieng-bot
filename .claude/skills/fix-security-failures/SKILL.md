---
name: fix-security-failures
description: Fix pip-audit security vulnerability failures. Use when CI fails due to pip-audit findings (CVE/GHSA). Handles both fixable and unfixable (upstream-only) vulnerabilities with graceful exit.
---

# Fix Security Failures (pip-audit)

## Step 1: Parse the Vulnerability Report

Search the failure logs for pip-audit findings:

```bash
grep -i "CVE-\|GHSA-\|vulnerability\|Found.*vulnerability\|pip-audit" .failure-logs.txt | head -100
```

Extract for each finding:
- **Package name** (e.g., `requests`)
- **Installed version** (e.g., `2.28.0`)
- **Vulnerability ID** (e.g., `GHSA-xxxx-xxxx-xxxx` or `CVE-2024-xxxxx`)
- **Fix version** if listed (pip-audit often states `Fix versions: X.Y.Z`)

pip-audit output format to recognize:
```
requests 2.28.0    GHSA-xxxx   Fix versions: 2.31.0
filelock 3.12.0    CVE-2024-x  Fix versions: (none)
```

## Step 2: For Each Vulnerable Package — Check PyPI for a Patched Version

### 2a. If pip-audit already lists fix versions

Use those directly — skip to Step 3.

### 2b. If no fix version is listed, check PyPI

```bash
# Check all available versions on PyPI
pip index versions <package-name> 2>/dev/null | head -5

# Or query the PyPI JSON API directly
curl -s "https://pypi.org/pypi/<package-name>/json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
versions = sorted(data['releases'].keys())
print('Available versions:', versions[-10:])
print('Latest:', data['info']['version'])
"
```

### 2c. Determine if a patch exists

A patch exists if there is **any published version higher than the installed version** that is NOT listed in the vulnerability's `fixed_in` exclusions.

**No patch exists** if:
- pip-audit explicitly states `Fix versions: (none)` or `No fix available`
- The PyPI API shows no newer releases
- The vulnerability advisory (GHSA/CVE) states the fix requires changes in a **dependency of the package** (i.e., the vulnerable code is in a transitive dependency that the package author hasn't yet updated)
- The latest PyPI version is the same as or older than the installed version

## Step 3: Apply the Fix (only if a patch version exists)

Update the version constraint in `pyproject.toml`:

```bash
# Find current constraint
grep -n "<package-name>" pyproject.toml
```

Edit `pyproject.toml` to require the patched minimum version:
- Change `"package>=1.0"` → `"package>=<fix-version>"`
- Or add a lower bound: `"package"` → `"package>=<fix-version>"`

Then regenerate the lock file:

```bash
uv lock
uv sync
```

Verify pip-audit now passes locally:

```bash
uv run pip-audit
```

If clean, commit:

```bash
git add pyproject.toml uv.lock
git commit -m "chore: bump <package> to <fix-version> to fix <CVE/GHSA-ID>

Co-authored-by: aieng-bot <aieng-bot@vectorinstitute.ai>"
```

## Step 4: Graceful Exit When No Patch Is Available

**This is the critical path.** If ANY vulnerability has no patched version available, do NOT attempt to fix it. The fix must come from the upstream library maintainers.

### Identify unfixable vulnerabilities

A vulnerability is unfixable if Step 2 confirms no patch version exists on PyPI.

### Post a PR comment explaining the situation

```bash
PR_NUMBER=$(cat .pr-context.json | python3 -c "import sys,json; print(json.load(sys.stdin)['pr_number'])")
REPO=$(cat .pr-context.json | python3 -c "import sys,json; print(json.load(sys.stdin)['repo'])")

gh pr comment "$PR_NUMBER" --repo "$REPO" --body "## Security Vulnerability — No Patch Available Yet

aieng-bot found the following security vulnerabilities reported by pip-audit, but **cannot fix them automatically** because no patched version has been released to PyPI yet:

| Package | Version | Vulnerability | Status |
|---------|---------|---------------|--------|
| <package> | <version> | <CVE/GHSA> | No fix available on PyPI |

### Why this cannot be auto-fixed

The vulnerability exists in \`<package>\` itself (or one of its dependencies). A fix requires the upstream maintainers to release a new version. Once a patched release is published to PyPI, aieng-bot can re-run and apply the update automatically.

### Recommended next steps

1. Monitor the vulnerability advisory for a patch release
2. Check if a \`pip-audit\` ignore/exception can be added temporarily with justification (requires human review)
3. Consider whether this dependency can be replaced with an alternative

_This PR will not be auto-merged until the vulnerability is resolved._"
```

### Exit without making any changes

Do **not** modify `pyproject.toml`, `uv.lock`, or any other file. Do **not** commit anything. Stop here and let the human team handle it.

## Step 5: Mixed Case — Some Fixable, Some Not

If a PR has multiple vulnerabilities where some have patches and some don't:

1. Fix all the patchable ones (Step 3)
2. Post a comment listing the unfixable ones (Step 4 comment template)
3. Do NOT merge the PR — leave it for human review
4. Push the partial fixes so CI can re-run and confirm the remaining vulnerabilities

## Common Mistakes to Avoid

- **Do not pin to an exact version** (e.g., `==2.31.0`) — use a minimum bound (`>=2.31.0`) to allow future patch upgrades
- **Do not ignore or suppress pip-audit findings** with `--ignore-vuln` unless a human has explicitly approved it
- **Do not assume transitive dependency bumps are safe** — always run `uv sync` and check that tests still pass after bumping
- **Do not mark the PR as fixed** if an unfixable vulnerability remains — the CI will still fail
