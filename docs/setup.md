# aieng-bot - Setup Guide

## Overview

aieng-bot is an AI-powered tool that autonomously fixes CI failures, resolves merge conflicts, and merges GitHub pull requests. It can be used via CLI on any PR, or configured with GitHub workflows to automatically monitor and fix bot PRs (Dependabot, pre-commit-ci) across an organization.

## Prerequisites

- Admin access to VectorInstitute organization
- Anthropic API key
- GitHub Personal Access Token with org-wide permissions

## Setup Steps

### 1. Create Anthropic API Key

1. Go to [Anthropic Console](https://console.anthropic.com/settings/keys)
2. Click "Create API Key"
3. Copy the key (starts with `sk-ant-...`)
4. Keep it secure - you'll add it as a secret

### 2. Create GitHub Personal Access Token

**Option A: Fine-grained Token (Recommended)**

1. Go to [Fine-grained tokens](https://github.com/settings/tokens?type=beta)
2. Click "Generate new token"
3. Configure:
   - **Token name**: `aieng-bot-org-access`
   - **Expiration**: 1 year
   - **Resource owner**: VectorInstitute
   - **Repository access**: All repositories
   - **Permissions**:
     - `contents`: Read and write
     - `pull_requests`: Read and write
     - `issues`: Read and write
     - `metadata`: Read-only (automatic)
4. Click "Generate token"
5. Copy the token (starts with `github_pat_...`)

**Option B: Classic Token**

1. Go to [Personal access tokens (classic)](https://github.com/settings/tokens)
2. Configure:
   - **Scopes**: `repo`, `workflow`, `read:org`
3. Generate and copy token

### 3. Add Secrets to This Repository

1. Go to `VectorInstitute/aieng-bot` → Settings → Secrets and variables → Actions
2. Add two secrets:
   - `ANTHROPIC_API_KEY`: Your Anthropic API key
   - `ORG_ACCESS_TOKEN`: Your GitHub PAT

### 4. Enable GitHub Actions

1. Go to Actions tab
2. Enable workflows if disabled
3. Verify workflows appear:
   - `discover-and-dispatch.yml`
   - `fix-pr-agent.yml`

### 5. Test the Setup

**Via CLI (recommended):**
```bash
# Fix a PR directly
aieng-bot fix --repo owner/repo --pr 123

# Fix with dashboard logging
aieng-bot fix --repo owner/repo --pr 123 --log
```

**Via GitHub Workflow:**
```bash
# Trigger fix workflow for a specific PR
gh workflow run fix-pr-agent.yml \
  --field target_repo="owner/repo" \
  --field pr_number="123"

# Run bot PR discovery (VectorInstitute org)
gh workflow run discover-and-dispatch.yml
```

**Via GitHub UI:**
Actions → Select workflow → Run workflow

### 6. Verify Bot Operation

After setup, the bot should:
- Run daily at 00:00 UTC
- Scan all VectorInstitute repositories
- Find open bot PRs (Dependabot and pre-commit-ci)
- Classify failures using Claude Haiku 4.5
- Auto-merge PRs with passing checks
- Fix failing PRs using Claude Sonnet 4.5

## Configuration

### Adjust Monitoring Frequency

Edit `.github/workflows/discover-and-dispatch.yml`:
```yaml
on:
  schedule:
    - cron: '0 0 * * *'    # Daily at midnight (default)
    # - cron: '0 */6 * * *'  # Every 6 hours
    # - cron: '0 */12 * * *' # Every 12 hours
```

### Change Claude Model

Set `CLAUDE_MODEL` environment variable to override defaults:
- Classification: `claude-haiku-4-5-20251001`
- Fixing: `claude-sonnet-4-5-20250929`

### Customize Fix Skills

Edit skill definitions in `.claude/skills/`:
- `fix-merge-conflicts.md`
- `fix-test-failures.md`
- `fix-lint-failures.md`
- `fix-security-audit.md`
- `fix-build-failures.md`

## Security Considerations

### Token Permissions
- Use fine-grained token when possible
- Set token expiration and rotate annually
- Monitor usage in GitHub audit log
- Never commit tokens to repository

### API Key Protection
- Monitor API usage in Anthropic Console
- Rotate key periodically

## Troubleshooting

### Bot Not Finding PRs
```bash
# Test token access
gh api orgs/VectorInstitute/repos -H "Authorization: token $ORG_ACCESS_TOKEN"
```

### Bot Can't Merge PRs
- Ensure auto-merge enabled in target repo
- Check branch protection rules
- Verify token has `contents: write`

### Claude API Errors
- Verify API key at [Anthropic Console](https://console.anthropic.com)
- Check quota and rate limits

### Workflow Not Running
- Verify Actions enabled
- Check secrets are set
- Cron uses UTC timezone

## Maintenance

### Weekly
- Review workflow runs for errors
- Check PR comments for bot activity

### Monthly
- Review merged PRs for quality
- Update skill templates based on patterns
- Check for model updates

---

🤖 *aieng-bot - AI-powered PR maintenance by Vector Institute AI Engineering*
