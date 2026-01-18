---
name: merge-pr
description: Rebase and merge a PR that's ready. Handles checking if rebase is needed, rebasing, waiting for CI, and merging.
allowed-tools: Read, Bash, Glob, Grep
---

# Merge PR

You are the AI Engineering Maintenance Bot merging a PR in a Vector Institute repository.

## Context
Read `.pr-context.json` for PR details (repo, pr_number, head_ref, base_ref).

## Process

### 1. Check if Rebase is Needed

```bash
# Fetch latest from remote
git fetch origin

# Check if base branch has commits not in the PR branch
BEHIND=$(git rev-list --count HEAD..origin/{base_ref})
echo "PR branch is $BEHIND commits behind {base_ref}"
```

If `$BEHIND` is greater than 0, the PR needs rebasing.

### 2. Rebase if Needed

```bash
# Rebase onto the base branch
git rebase origin/{base_ref}

# If conflicts occur, resolve them (see fix-merge-conflicts skill)
# After resolving:
git rebase --continue

# Force push the rebased branch
git push origin HEAD:{head_ref} --force-with-lease
```

**IMPORTANT**: Use `--force-with-lease` to safely force push after rebase.

### 3. Wait for CI After Rebase

If you rebased, wait for CI to complete:

```bash
# Check CI status
gh pr checks {pr_number} --repo {repo}
```

Poll every 30-60 seconds until all checks pass or fail. Do NOT use bash loops - run the command, check output, `sleep 30`, repeat manually.

If CI fails after rebase, analyze the failures and fix them (use appropriate fix skill).

### 4. Merge the PR

Once all checks pass:

```bash
# Squash merge the PR
gh pr merge {pr_number} --repo {repo} --squash --delete-branch
```

If the PR is from Dependabot or pre-commit-ci, squash merge is preferred to keep history clean.

## Important Rules

- Always fetch latest before checking rebase status
- Use `--force-with-lease` (not `--force`) when pushing after rebase
- Wait for CI to pass after rebase before merging
- Use squash merge for bot PRs to keep history clean
- Delete the branch after merge (`--delete-branch`)

## Commit Message for Rebase Conflicts

If you need to resolve conflicts during rebase:

```
Resolve rebase conflicts with {base_ref}

- [Description of conflicts resolved]

Co-authored-by: AI Engineering Maintenance Bot <aieng-bot@vectorinstitute.ai>
```
