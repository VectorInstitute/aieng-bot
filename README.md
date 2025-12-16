# aieng-bot-maintain

Centralized maintenance bot that automatically manages Dependabot PRs across all Vector Institute repositories from a single location.

## Features

- **Organization-wide monitoring** - Scans all VectorInstitute repos every 6 hours
- **Auto-merge** - Merges Dependabot PRs when all checks pass
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
│  2. Finds Dependabot PRs        │
│  3. Checks status               │
│  4. Merges or fixes PRs         │
└──────────────┬──────────────────┘
               │
               │ Operates on
               ▼
┌───────────────────────────────────┐
│   VectorInstitute Organization    │
│                                   │
│  ├─ repo-1  (Dependabot PR #1)    │
│  ├─ repo-2  (Dependabot PR #2)    │
│  ├─ repo-3  (Dependabot PR #3)    │
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
- Scans all VectorInstitute repositories for open Dependabot PRs
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
- `monitor-org-dependabot.yml` - Scans org for Dependabot PRs every 6 hours
- `fix-remote-pr.yml` - Fixes failing PRs using AI

**AI Prompt Templates** (customize for your needs)
- `fix-test-failures.md` - Test failure resolution strategies
- `fix-lint-failures.md` - Linting/formatting fixes
- `fix-security-audit.md` - Security vulnerability handling
- `fix-build-failures.md` - Build/compilation error fixes

## Capabilities

**Can fix:**
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
gh workflow run monitor-org-dependabot.yml

# Fix a specific PR (test with aieng-template-mvp#17)
gh workflow run fix-remote-pr.yml \
  --field target_repo="VectorInstitute/aieng-template-mvp" \
  --field pr_number="17"
```

**Trigger via GitHub UI:**
Actions → Select workflow → Run workflow → Enter parameters

## Monitoring

**View bot activity:**
- Actions tab - All workflow runs and success/failure rates
- PR comments - Detailed status updates on each PR
- Run summary - PR count and actions taken per run

**Debug commands:**
```bash
# View recent workflow runs
gh run list --workflow=monitor-org-dependabot.yml --limit 5

# View logs for specific run
gh run view RUN_ID --log
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
