# aieng-bot-maintain

Centralized maintenance bot for ALL Vector Institute repositories. Automatically manages Dependabot PRs across the entire organization from a single location.

## Features

- **Organization-wide monitoring**: Scans all VectorInstitute repos every 10 minutes
- **Auto-merge**: Merges Dependabot PRs when all checks pass
- **Auto-fix**: Fixes test failures, linting issues, security vulnerabilities, and build errors using Gemini 3 AI
- **Centralized operation**: No need to install workflows in each repository
- **Smart detection**: Categorizes failures and applies appropriate fix strategies
- **Transparent**: Comments on PRs with status updates

## Architecture

```
┌─────────────────────────────────┐
│  aieng-bot-maintain Repository  │
│  (This Repo - Central Bot)      │
│                                  │
│  Runs every 10 minutes:         │
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
│                                    │
│  ├─ repo-1  (Dependabot PR #1)    │
│  ├─ repo-2  (Dependabot PR #2)    │
│  ├─ repo-3  (Dependabot PR #3)    │
│  └─ repo-N  ...                   │
└───────────────────────────────────┘
```

## Quick Start

### One-Time Setup (in THIS repository)

1. **Add organization secrets** to this repository:
   - `GEMINI_API_KEY`: Get from [Google AI Studio](https://makersuite.google.com/app/apikey)
   - `ORG_ACCESS_TOKEN`: GitHub PAT with org-wide access (see below)

2. **Create GitHub Personal Access Token**:
   - Go to Settings → Developer settings → Personal access tokens → Fine-grained tokens
   - Create token with:
     - Resource owner: VectorInstitute
     - Repository access: All repositories
     - Permissions: `contents: write`, `pull_requests: write`, `issues: write`
   - Add as secret: `ORG_ACCESS_TOKEN`

3. **Enable workflows** in this repository:
   - Actions → Enable workflows
   - Workflows will start running automatically

4. **That's it!** The bot now monitors all VectorInstitute repos

## How It Works

### 1. Monitoring (Every 10 minutes)
`monitor-org-dependabot.yml` runs automatically:
- Scans all VectorInstitute repositories
- Finds open Dependabot PRs
- Checks status of each PR
- Routes to merge or fix workflows

### 2. Auto-Merge (for passing PRs)
When all checks pass:
- Approves the PR
- Enables auto-merge
- Comments with status
- PR merges automatically when ready

### 3. Auto-Fix (for failing PRs)
When checks fail:
- Triggers `fix-remote-pr.yml` workflow
- Clones the target repo + PR branch
- Analyzes failure type (test/lint/security/build)
- Loads appropriate AI prompt template
- Invokes Gemini 3 Pro to generate fixes
- Pushes fixes to PR branch
- Comments with results

## Configuration

### Required Secrets
- `GEMINI_API_KEY`: Gemini API access (required)
- `ORG_ACCESS_TOKEN`: GitHub PAT with org-wide permissions (required)

### Workflows
- `.github/workflows/monitor-org-dependabot.yml` - Scans org for Dependabot PRs
- `.github/workflows/fix-remote-pr.yml` - Fixes failing PRs

### AI Prompt Templates
Customize these for your organization's needs:
- `.github/prompts/fix-test-failures.md`
- `.github/prompts/fix-lint-failures.md`
- `.github/prompts/fix-security-audit.md`
- `.github/prompts/fix-build-failures.md`

## What It Can Fix

✅ Linting and formatting issues
✅ Security vulnerabilities (dependency updates)
✅ Simple test failures from API changes
✅ Build configuration issues

❌ Complex logic errors
❌ Breaking changes requiring refactoring
❌ Issues requiring architectural decisions

## Manual Testing

You can manually trigger workflows for specific PRs:

```bash
# Test the monitor workflow
gh workflow run monitor-org-dependabot.yml --repo VectorInstitute/aieng-bot-maintain

# Fix a specific PR
gh workflow run fix-remote-pr.yml \
  --repo VectorInstitute/aieng-bot-maintain \
  --field target_repo="VectorInstitute/aieng-template-mvp" \
  --field pr_number="17"
```

Or use the GitHub UI:
- Actions → Select workflow → Run workflow → Enter parameters

## Documentation

- [Setup Guide](SETUP.md): Detailed configuration and permissions
- [Deployment Guide](DEPLOYMENT.md): Rollout strategy and monitoring
- [Testing Guide](TESTING.md): Test cases and validation
- [Bot Identity](/.github/bot-assets/BOT_IDENTITY.md): Avatar and branding specs

## Test Target

Test with [aieng-template-mvp#17](https://github.com/VectorInstitute/aieng-template-mvp/pull/17):
- Has frontend test failures
- Real Dependabot dependency updates
- Perfect candidate for auto-fix testing

## Monitoring

View bot activity:
- **Actions tab**: See all workflow runs
- **Workflow runs**: Check success/failure rates
- **PR comments**: Bot leaves detailed status updates
- **Run summary**: Each workflow run shows PR count and actions taken

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Workflow doesn't run | Check Actions enabled, verify secrets set |
| Can't find PRs | Verify `ORG_ACCESS_TOKEN` has correct permissions |
| Can't merge PRs | Ensure token has `contents: write` permission |
| Can't push fixes | Check token has write access to target repos |
| Gemini errors | Verify `GEMINI_API_KEY` is set and has quota |
| Rate limits | Reduce monitoring frequency in cron schedule |

**Debug workflow**:
```bash
# View recent runs
gh run list --workflow=monitor-org-dependabot.yml --limit 5

# View specific run logs
gh run view RUN_ID --log
```

## Contributing

Contributions welcome. Please test thoroughly before submitting PRs.

## License

[Add appropriate license]

---

🤖 *AI Engineering Maintenance Bot - Maintaining Vector Institute Repositories built by AI Engineering*
