---
name: merge-pr
description: Merge a PR after CI passes. Use when all checks have passed and PR is ready to merge.
allowed-tools: Bash
---

# Merge PR

Merges a PR that has passed all CI checks.

## Scope

**This skill DOES:**
- Merge the PR using squash merge
- Delete the branch after merge

**Prerequisites (main loop ensures these):**
- All CI checks have passed
- Branch is up to date with base

## Process

### Merge the PR

```bash
# Read PR details
PR_NUMBER=$(jq -r '.pr_number' .pr-context.json)
REPO=$(jq -r '.repo' .pr-context.json)

# Squash merge and delete branch
gh pr merge $PR_NUMBER --repo $REPO --squash --delete-branch
```

## Important Rules
- Only merge when all CI checks pass
- Use squash merge for bot PRs to keep history clean
- Delete the branch after merge (`--delete-branch`)
