# aieng-bot

----------------------------------------------------------------------------------------

[![PyPI](https://img.shields.io/pypi/v/aieng-bot)](https://pypi.org/project/aieng-bot)
[![code checks](https://github.com/VectorInstitute/aieng-bot/actions/workflows/code_checks.yml/badge.svg)](https://github.com/VectorInstitute/aieng-bot/actions/workflows/code_checks.yml)
[![unit tests](https://github.com/VectorInstitute/aieng-bot/actions/workflows/unit_tests.yml/badge.svg)](https://github.com/VectorInstitute/aieng-bot/actions/workflows/unit_tests.yml)
[![docs](https://github.com/VectorInstitute/aieng-bot/actions/workflows/docs.yml/badge.svg)](https://github.com/VectorInstitute/aieng-bot/actions/workflows/docs.yml)
[![codecov](https://codecov.io/github/VectorInstitute/aieng-bot/graph/badge.svg?token=83MYFZ3UPA)](https://codecov.io/github/VectorInstitute/aieng-bot)
![GitHub License](https://img.shields.io/github/license/VectorInstitute/aieng-bot)


AI-powered tool that autonomously fixes CI failures, resolves merge conflicts, and merges GitHub pull requests using Claude AI.

## Features

- **Fix any PR** - Use the CLI to fix CI failures on any GitHub pull request
- **Auto-fix** - Automatically fixes test failures, linting issues, security vulnerabilities, merge conflicts, and build errors
- **Smart classification** - Categorizes failures and applies appropriate fix strategies
- **Organization-wide automation** - Includes workflows to scan VectorInstitute repos daily for bot PRs (Dependabot, pre-commit-ci)
- **Observable** - Full execution tracing with dashboard analytics
- **Transparent** - Comments on PRs with status updates

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  aieng-bot                                                  │
│                                                             │
│  CLI Usage (any PR):                                        │
│    aieng-bot fix --repo owner/repo --pr 123                 │
│                                                             │
│  Automated Workflows (bot PRs only):                        │
│    Daily scan (00:00 UTC) for Dependabot/pre-commit-ci PRs  │
│    with failing checks across VectorInstitute org           │
└─────────────────────────────────────────────────────────────┘
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

**1. Classification**
- Analyzes PR and failure logs using Claude Haiku 4.5
- Categorizes failure type: test, lint, security, build, or merge conflict
- Routes to appropriate fix strategy

**2. Fix Loop**
- Clones target repository and PR branch
- Loads appropriate AI prompt template for the failure type
- Uses Claude Agent SDK to automatically apply fixes
- Commits and pushes fixes to PR
- Polls CI status, retries on failure (up to max_retries)

**3. Merge**
- Auto-merges when all checks pass
- Comments on PR with status updates

**Automated Bot PR Monitoring** (optional, for VectorInstitute org)
- Daily scan at 00:00 UTC for Dependabot/pre-commit-ci PRs with failures
- Automatically dispatches fix jobs for discovered PRs

## Configuration

**Required Secrets**
- `ANTHROPIC_API_KEY` - Anthropic API access for Claude
- `ORG_ACCESS_TOKEN` - GitHub PAT with org-wide permissions

**Model Configuration**
- Classification: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) - cost-efficient
- Fixing: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) - agentic capability
- Override with `CLAUDE_MODEL` environment variable

**Workflows**
- `discover-and-dispatch.yml` - Daily scan (00:00 UTC) for Dependabot/pre-commit-ci PRs with failures
- `fix-pr-agent.yml` - Per-PR agent workflow (6-hour timeout), can be triggered manually for any PR
- `code_checks.yml` - Ruff + mypy checks
- `unit_tests.yml` - pytest suite

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

## CLI Usage

```bash
# Install dependencies
uv sync

# Fix and merge a PR
aieng-bot fix --repo owner/repo --pr 123

# Fix with dashboard logging
aieng-bot fix --repo owner/repo --pr 123 --log

# Custom retries and timeout
aieng-bot fix --repo owner/repo --pr 123 --max-retries 5 --timeout-minutes 180
```

## Manual Testing

**Trigger via CLI:**
```bash
# Fix a PR using the CLI (recommended)
aieng-bot fix --repo owner/repo --pr 123

# Or trigger via GitHub workflow
gh workflow run fix-pr-agent.yml \
  --field target_repo="owner/repo" \
  --field pr_number="123"

# Run the bot PR discovery workflow (VectorInstitute org only)
gh workflow run discover-and-dispatch.yml
```

**Trigger via GitHub UI:**
Actions → Select workflow → Run workflow → Enter parameters

## Dashboard

**View comprehensive analytics and agent execution traces:**
- 📊 **[Dashboard](https://platform.vectorinstitute.ai/aieng-bot)** - Interactive dashboard with:
  - Overview table of all PR fixes
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

**View activity:**
- [Dashboard](https://platform.vectorinstitute.ai/aieng-bot) - Comprehensive analytics and traces
- Actions tab - All workflow runs and success/failure rates
- PR comments - Detailed status updates on each PR
- Run summary - PR count and actions taken per run

**Debug commands:**
```bash
# View recent workflow runs
gh run list --workflow=discover-and-dispatch.yml --limit 5

# View logs for specific run
gh run view RUN_ID --log
```

## Documentation

- [Setup Guide](docs/setup.md) - Configuration and permissions
- [Deployment Guide](docs/deployment.md) - Rollout and monitoring

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

🤖 *aieng-bot - AI-powered PR maintenance by Vector Institute AI Engineering*
