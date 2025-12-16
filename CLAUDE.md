# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**aieng-bot-maintain** is a centralized GitHub Actions bot that automatically manages Dependabot PRs across all VectorInstitute organization repositories. It operates from this single repository and requires no installation in target repos.

## Core Architecture

### Workflow System
The bot uses two main GitHub Actions workflows that work together:

1. **monitor-org-dependabot.yml** (Runs every 6 hours)
   - Scans all VectorInstitute repositories for open Dependabot PRs
   - Analyzes PR status (passing/failing checks)
   - Auto-merges PRs with passing checks
   - Triggers fix workflow for failing PRs

2. **fix-remote-pr.yml** (Triggered on-demand)
   - Clones the target repository PR branch
   - Analyzes failure type (test/lint/security/build)
   - Loads appropriate AI prompt template
   - Invokes Claude Agent SDK to apply fixes automatically
   - Pushes fixes to PR branch

### Failure Detection and Routing
The bot categorizes failures by examining check names (fix-remote-pr.yml:69-99):
- **Test failures**: Names matching `test|spec|jest|pytest|unittest`
- **Lint failures**: Names matching `lint|format|pre-commit|eslint|prettier|black|flake8|ruff`
- **Security failures**: Names matching `audit|security|snyk|dependabot|pip-audit`
- **Build failures**: Names matching `build|compile|webpack|vite|tsc`

Each category routes to a specific prompt template in `.github/prompts/`.

### AI Prompt System
Prompt templates use placeholder substitution (fix-remote-pr.yml:127-167):
- `{{REPO_NAME}}` - Target repository
- `{{PR_NUMBER}}` - PR number
- `{{PR_TITLE}}` - PR title
- `{{PR_AUTHOR}}` - PR author (usually dependabot)
- `{{FAILED_CHECK_NAME}}` - Comma-separated failed check names
- `{{FAILURE_DETAILS}}` - Last 5000 lines of failure logs

### Claude Agent SDK Integration
The bot uses the Claude Agent SDK (https://platform.claude.com/docs/en/agent-sdk/overview) with Claude Sonnet 4.5. The Agent SDK autonomously reads code, analyzes failures, and applies fixes directly to files using built-in tools (Read, Edit, Bash, Glob, Grep).

## Common Commands

### Manual Workflow Triggers

Trigger organization-wide scan:
```bash
gh workflow run monitor-org-dependabot.yml --repo VectorInstitute/aieng-bot-maintain
```

Fix specific PR:
```bash
gh workflow run fix-remote-pr.yml \
  --repo VectorInstitute/aieng-bot-maintain \
  --field target_repo="VectorInstitute/repo-name" \
  --field pr_number="123"
```

Test with example failing PR:
```bash
gh workflow run fix-remote-pr.yml \
  --repo VectorInstitute/aieng-bot-maintain \
  --field target_repo="VectorInstitute/aieng-template-mvp" \
  --field pr_number="17"
```

### Debugging

View recent workflow runs:
```bash
gh run list --workflow=monitor-org-dependabot.yml --limit 5
```

View logs for specific run:
```bash
gh run view RUN_ID --log
```

Test organization access:
```bash
gh api orgs/VectorInstitute/repos
```

## Configuration

### Required Secrets
Set in repository Settings → Secrets and variables → Actions:
- `ANTHROPIC_API_KEY` - Get from Anthropic Console (https://console.anthropic.com/settings/keys)
- `ORG_ACCESS_TOKEN` - GitHub PAT with org-wide permissions (see SETUP.md for details)

### Monitoring Frequency
Edit `.github/workflows/monitor-org-dependabot.yml:6`:
```yaml
- cron: '0 */6 * * *'  # Current: every 6 hours
```

### Claude Model Configuration
The bot uses Claude Sonnet 4.5 via the Agent SDK. The model is configured automatically through the `ANTHROPIC_API_KEY` and uses the latest Sonnet model available.

### Customize Fix Behavior
Edit prompt templates in `.github/prompts/`:
- `fix-test-failures.md` - Test failure resolution strategies
- `fix-lint-failures.md` - Linting/formatting fixes
- `fix-security-audit.md` - Security vulnerability handling
- `fix-build-failures.md` - Build/compilation error fixes

Add repository-specific context or commands to these prompts.

### Filter Repositories
To exclude repos from monitoring, edit monitor-org-dependabot.yml after line 43:
```bash
REPOS=$(echo "$REPOS" | grep -v "repo-to-exclude")
```

## Key Design Patterns

### Centralized Operation
All bot logic lives in THIS repository. Target repositories need:
- Dependabot enabled (Settings → Security → Dependabot)
- Auto-merge enabled (Settings → General → Pull Requests) - optional but recommended
- No workflow files or bot-specific configuration

### Status Check Analysis
The bot filters out its own check (monitor-org-dependabot.yml:106) to avoid circular dependencies. Checks are considered passing if conclusion is `SUCCESS`, `NEUTRAL`, `SKIPPED`, or `null`.

### Commit Attribution
All bot commits include co-authorship (fix-remote-pr.yml:237):
```
Co-authored-by: AI Engineering Maintenance Bot <aieng-bot@vectorinstitute.ai>
```

Git config uses:
- Name: `aieng-bot-maintain[bot]`
- Email: `aieng-bot@vectorinstitute.ai`

### Error Handling
Both workflows use `continue-on-error: true` for critical steps to prevent blocking other PRs if one fails.

## Testing

Primary test target: [aieng-template-mvp#17](https://github.com/VectorInstitute/aieng-template-mvp/pull/17) - has real frontend test failures from Dependabot updates.

See TESTING.md for comprehensive test scenarios and validation procedures.

## Important Constraints

### What the Bot Can Fix
- Linting/formatting issues (auto-fixable)
- Security vulnerabilities (dependency updates)
- Simple test failures from API changes
- Build configuration issues

### What Requires Manual Intervention
- Complex logic errors
- Breaking changes requiring refactoring
- Architectural decisions
- Issues the AI cannot understand from logs alone

### Safety Guardrails
Prompt templates explicitly instruct the AI to:
- Make minimal changes only
- Not skip tests or disable checks
- Not add `@ts-ignore`, `// eslint-disable`, or `# noqa` without justification
- Preserve original functionality and intent
- Follow existing code patterns

## Bot Identity

Avatar and branding assets are in `.github/bot-assets/`:
- `avatar.svg` - Vector graphic logo
- `avatar.webp` - Raster format
- `BOT_IDENTITY.md` - Design specifications

Signature used in all comments:
```
🤖 *AI Engineering Maintenance Bot - Maintaining Vector Institute Repositories built by AI Engineering*
```

## Related Documentation

- **SETUP.md** - Detailed setup instructions, permissions, security
- **DEPLOYMENT.md** - Rollout strategy and monitoring
- **TESTING.md** - Test cases and validation procedures
- **README.md** - High-level overview and quick start
