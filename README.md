# aieng-bot-maintain

----------------------------------------------------------------------------------------

[![code checks](https://github.com/VectorInstitute/aieng-bot-maintain/actions/workflows/code_checks.yml/badge.svg)](https://github.com/VectorInstitute/aieng-bot-maintain/actions/workflows/code_checks.yml)
[![unit tests](https://github.com/VectorInstitute/aieng-bot-maintain/actions/workflows/unit_tests.yml/badge.svg)](https://github.com/VectorInstitute/aieng-bot-maintain/actions/workflows/unit_tests.yml)
[![docs](https://github.com/VectorInstitute/aieng-bot-maintain/actions/workflows/docs.yml/badge.svg)](https://github.com/VectorInstitute/aieng-bot-maintain/actions/workflows/docs.yml)
[![codecov](https://codecov.io/github/VectorInstitute/aieng-bot-maintain/graph/badge.svg?token=83MYFZ3UPA)](https://codecov.io/github/VectorInstitute/aieng-bot-maintain)
![GitHub License](https://img.shields.io/github/license/VectorInstitute/aieng-bot-maintain)


Centralized maintenance bot that automatically manages bot PRs (Dependabot and pre-commit-ci) across all Vector Institute repositories from a single location.

## Features

- **Organization-wide monitoring** - Scans all VectorInstitute repos every 6 hours
- **Auto-merge** - Merges bot PRs (Dependabot and pre-commit-ci) when all checks pass
- **Auto-fix** - Fixes test failures, linting issues, security vulnerabilities, and build errors using Claude AI Agent SDK
- **Centralized operation** - No installation needed in individual repositories
- **Smart detection** - Categorizes failures and applies appropriate fix strategies
- **Transparent** - Comments on PRs with status updates

## Architecture

```
┌─────────────────────────────────┐
│  aieng-bot-maintain Repository  │
│  (This Repo - Central Bot)      │
│                                 │
│  Runs every 6 hours:            │
│  1. Scans VectorInstitute org   │
│  2. Finds bot PRs               │
│  3. Checks status               │
│  4. Merges or fixes PRs         │
└──────────────┬──────────────────┘
               │
               │ Operates on
               ▼
┌───────────────────────────────────┐
│   VectorInstitute Organization    │
│                                   │
│  ├─ repo-1  (Bot PR #1)           │
│  ├─ repo-2  (Bot PR #2)           │
│  ├─ repo-3  (Bot PR #3)           │
│  └─ repo-N  ...                   │
└───────────────────────────────────┘
```

## Quick Start

### Setup (in this repository)

**1. Create Anthropic API Key**
- Get from [Anthropic Console](https://console.anthropic.com/settings/keys)
- Add as repository secret: `ANTHROPIC_API_KEY`

**2. Create GitHub Personal Access Token**
- Go to Settings → Developer settings → Personal access tokens → Fine-grained tokens
- Configure: Resource owner: `VectorInstitute`, Repository access: `All repositories`
- Permissions: `contents: write`, `pull_requests: write`, `issues: write`
- Add as repository secret: `ORG_ACCESS_TOKEN`

**3. Enable GitHub Actions**
- Go to Actions tab → Enable workflows

The bot now monitors all VectorInstitute repositories automatically.

## How It Works

**1. Monitor** (every 6 hours)
- Scans all VectorInstitute repositories for open bot PRs (Dependabot and pre-commit-ci)
- Checks status of each PR
- Routes to merge or fix workflow

**2. Auto-Merge** (when all checks pass)
- Approves PR and enables auto-merge
- Comments with status
- PR merges automatically

**3. Auto-Fix** (when checks fail)
- Clones target repository and PR branch
- Analyzes failure type: test, lint, security, or build
- Loads appropriate AI prompt template
- Uses Claude Agent SDK to automatically apply fixes
- Commits and pushes fixes to PR

## Configuration

**Required Secrets**
- `ANTHROPIC_API_KEY` - Anthropic API access for Claude
- `ORG_ACCESS_TOKEN` - GitHub PAT with org-wide permissions

**Workflows**
- `monitor-org-bot-prs.yml` - Scans org for bot PRs (Dependabot and pre-commit-ci) every 6 hours
- `fix-remote-pr.yml` - Fixes failing PRs using AI

**AI Prompt Templates** (customize for your needs)
- `fix-merge-conflicts.md` - Resolve merge conflicts with best practices
- `fix-test-failures.md` - Test failure resolution strategies
- `fix-lint-failures.md` - Linting/formatting fixes
- `fix-security-audit.md` - Security vulnerability handling
- `fix-build-failures.md` - Build/compilation error fixes

## Capabilities

**Can fix:**
- Merge conflicts (dependency files, lock files, code)
- Linting and formatting issues
- Security vulnerabilities (dependency updates)
- Simple test failures from API changes
- Build configuration issues

**Cannot fix:**
- Complex logic errors
- Breaking changes requiring refactoring
- Issues requiring architectural decisions

## Manual Testing

**Trigger via CLI:**
```bash
# Monitor all repositories
gh workflow run monitor-org-bot-prs.yml

# Fix a specific PR (test with aieng-template-mvp#17)
gh workflow run fix-remote-pr.yml \
  --field target_repo="VectorInstitute/aieng-template-mvp" \
  --field pr_number="17"
```

**Trigger via GitHub UI:**
Actions → Select workflow → Run workflow → Enter parameters

## Dashboard

**View comprehensive analytics and agent execution traces:**
- 📊 **[Bot Dashboard](https://catalog.vectorinstitute.ai/aieng-bot-maintain)** - Interactive dashboard with:
  - Overview table of all bot PR fixes
  - Success rates and performance metrics
  - Detailed agent execution traces (like LangSmith/Langfuse)
  - Code diffs with syntax highlighting
  - Failure analysis and reasoning timeline

**Features:**
- Real-time PR status tracking
- Agent observability (tool calls, reasoning, actions)
- Historical metrics and trends
- Per-repo and per-failure-type analytics
- Sortable/filterable PR table

**Authentication:**
- Restricted to @vectorinstitute.ai email addresses
- Google OAuth 2.0 sign-in

## Monitoring

**View bot activity:**
- [Dashboard](https://catalog.vectorinstitute.ai/aieng-bot-maintain) - Comprehensive analytics and traces
- Actions tab - All workflow runs and success/failure rates
- PR comments - Detailed status updates on each PR
- Run summary - PR count and actions taken per run

**Debug commands:**
```bash
# View recent workflow runs
gh run list --workflow=monitor-org-bot-prs.yml --limit 5

# View logs for specific run
gh run view RUN_ID --log

# Collect metrics manually
gh workflow run collect-bot-metrics.yml
```

## Documentation

- [Setup Guide](docs/setup.md) - Detailed configuration and permissions
- [Deployment Guide](docs/deployment.md) - Rollout strategy and monitoring
- [Testing Guide](docs/testing.md) - Test cases and validation

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Workflow doesn't run | Check Actions enabled and secrets are set |
| Can't find PRs | Verify `ORG_ACCESS_TOKEN` has correct permissions |
| Can't merge PRs | Ensure token has `contents: write` permission |
| Can't push fixes | Check token has write access to target repos |
| Claude API errors | Verify `ANTHROPIC_API_KEY` is valid |
| Rate limits | Reduce monitoring frequency in workflow cron schedule |

See [Setup Guide](docs/setup.md) for detailed troubleshooting.

---

🤖 *AI Engineering Maintenance Bot - Maintaining Vector Institute Repositories built by AI Engineering*
