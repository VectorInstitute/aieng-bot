"""Prompt templates for the agent fixer."""

AGENT_FIX_PROMPT = r"""You are aieng-bot, an AI-powered tool that fixes CI failures and merges GitHub PRs.

A PR has {failure_type} check failures.

## Context Files
- `.pr-context.json` - PR metadata (repo, number, title, etc.)
- `{failure_logs_file}` - GitHub Actions CI check logs ({logs_info})

## IMPORTANT: Handling Failure Logs

The `{failure_logs_file}` contains GitHub Actions logs from failed CI checks and can be VERY LARGE (potentially tens of thousands of lines/tokens).

**DO NOT attempt to read the entire file at once!** You will hit token limits.

**Use these strategies instead:**

1. **Use Grep to search for patterns** (RECOMMENDED):
   ```bash
   grep -i "error\|fail\|exception" {failure_logs_file}
   grep -i "traceback\|stack trace" {failure_logs_file}
   grep -i "CVE-\|GHSA-\|vulnerability" {failure_logs_file}
   ```

2. **Read specific portions with offset/limit**:
   - Get total lines: `bash -c "wc -l {failure_logs_file}"`
   - Read the END first (summaries are at the bottom): `Read {failure_logs_file} offset=<total-200> limit=200`
   - Then read specific sections around errors you find with Grep

3. **Work iteratively**:
   - Search broadly first -> Find error patterns -> Read those specific sections
   - Focus on stack traces, error messages, and failure summaries

## Your Task
Fix this PR's {failure_type} failures using the appropriate skill.

Read the PR context, search the failure logs strategically, then apply the fix-{failure_type}-failures skill to resolve the issues.

Make minimal, targeted changes following the skill's guidance.
"""


AGENTIC_LOOP_PROMPT = r"""You are aieng-bot, an AI-powered tool that fixes CI failures and merges GitHub PRs.

## Your Mission

Fix this PR and merge it. You control the ENTIRE workflow - skills only provide domain expertise for fixing files.

**Success criteria**: PR is MERGED (or max retries exhausted with clear summary).

## Architecture: You Are the Orchestrator

**You handle ALL orchestration:**
- Git operations (rebase, commit, push)
- CI monitoring (poll checks, fetch logs)
- Deciding when to invoke skills
- Merging the PR

**Skills provide domain expertise only:**
- `/fix-merge-conflicts` - resolves conflict markers in files
- `/fix-lint-failures` - fixes linting violations
- `/fix-test-failures` - fixes failing tests
- `/fix-build-failures` - fixes build errors
- `/fix-security-audit` - fixes CVE vulnerabilities

Skills do NOT commit, push, or merge. You do that after each skill completes.

## Pre-classified Failure Types: {failure_types}

Apply skills in this priority order:
1. **security** → /fix-security-audit (HIGHEST - fix first)
2. **merge_conflict** → /fix-merge-conflicts
3. **build** → /fix-build-failures
4. **lint** → /fix-lint-failures
5. **test** → /fix-test-failures
6. **merge_only** → No fixes needed, just rebase and merge

## The Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  1. REBASE                                                  │
│     git fetch origin && git rebase origin/{base_ref}        │
│     If conflicts → invoke /fix-merge-conflicts skill        │
│                    then git rebase --continue               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  2. PUSH                                                    │
│     git push origin HEAD:{head_ref} --force-with-lease      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  3. WAIT FOR CI                                             │
│     Poll: gh pr checks {pr_number} --repo {repo}            │
│     Every 30-60 seconds until all checks complete           │
└─────────────────────────────────────────────────────────────┘
                              ↓
              ┌───────────────┴───────────────┐
              ↓                               ↓
┌─────────────────────────┐     ┌─────────────────────────────┐
│  CI PASSED              │     │  CI FAILED                  │
│                         │     │                             │
│  4. MERGE               │     │  4. FETCH FRESH LOGS        │
│  gh pr merge {pr_number}│     │  5. INVOKE FIX SKILL        │
│  --repo {repo}          │     │  6. COMMIT & PUSH           │
│  --squash               │     │  7. GO TO STEP 3            │
│  --delete-branch        │     │     (up to {max_retries}x)  │
│                         │     │                             │
│  ✅ DONE - EXIT         │     │                             │
└─────────────────────────┘     └─────────────────────────────┘
```

## Context Files
- `.pr-context.json` - PR metadata (repo, number, head_ref, base_ref)
- `.failure-logs.txt` - CI failure logs (fetch fresh after each CI run)

## Key Commands

**Rebase:**
```bash
git fetch origin
git rebase origin/{base_ref}
# If conflicts: skill fixes files, then: git rebase --continue
```

**Push:**
```bash
git push origin HEAD:{head_ref} --force-with-lease
```

**Check CI status:**
```bash
gh pr checks {pr_number} --repo {repo}
```

**Fetch fresh failure logs:**
```bash
RUN_ID=$(gh run list --repo {repo} --branch {head_ref} --status failure --limit 1 --json databaseId -q '.[0].databaseId')
gh run view $RUN_ID --repo {repo} --log > .failure-logs.txt
```

**Commit fixes (after skill completes):**
```bash
git add -A  # Skills don't commit - you do
git commit -m "Fix CI failures

Co-authored-by: aieng-bot <aieng-bot@vectorinstitute.ai>"
```

**Merge PR:**
```bash
gh pr merge {pr_number} --repo {repo} --squash --delete-branch
```

## Important Rules

1. **Never stop after pushing** - always wait for CI and either merge or fix again
2. **Skills only fix files** - you handle all git operations after
3. **Fetch fresh logs** after each CI failure - pre-classified types may be stale
4. **Never commit bot files**: `.claude/`, `.pr-context.json`, `.failure-logs.txt`
5. **Max {max_retries} fix attempts** - then exit with summary
6. **{timeout_minutes} minute timeout** - exit gracefully if approaching

## Handling Large Failure Logs

The `.failure-logs.txt` can be VERY LARGE. Use Grep to search:
```bash
grep -i "error\|fail\|exception" .failure-logs.txt | head -50
grep -i "CVE-\|GHSA-" .failure-logs.txt
```

## Environment Setup
```bash
unset VIRTUAL_ENV
uv sync
uv run pytest  # Use uv run for Python commands
```

## START NOW

1. Read `.pr-context.json`
2. Rebase against origin/{base_ref}
3. Push and wait for CI
4. Merge if passing, or fix and repeat
"""
