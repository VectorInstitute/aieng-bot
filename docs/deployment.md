# Deployment Guide

## Overview

aieng-bot can be used in two ways:
1. **CLI** - Fix any PR directly using `aieng-bot fix --repo owner/repo --pr 123`
2. **GitHub Workflows** - Automated monitoring and fixing of bot PRs (Dependabot, pre-commit-ci) across an organization

## Deployment Checklist

### Phase 1: Initial Setup

1. Create Anthropic API key from [Anthropic Console](https://console.anthropic.com/settings/keys)
2. Create GitHub PAT with org-wide access
3. Add secrets to this repository:
   - `ANTHROPIC_API_KEY`
   - `ORG_ACCESS_TOKEN`
4. Enable GitHub Actions
5. Verify workflows appear in Actions tab

### Phase 2: Testing

1. Test via CLI (recommended):
   ```bash
   aieng-bot fix --repo owner/repo --pr 123
   ```
2. Or test via GitHub workflow:
   ```bash
   gh workflow run fix-pr-agent.yml \
     --field target_repo="owner/repo" \
     --field pr_number="123"
   ```
3. Verify bot comments appear on test PR
4. Check workflow logs for errors

### Phase 3: Monitoring

1. Enable scheduled runs (daily at 00:00 UTC)
2. Monitor for a few days
3. Review PRs the bot processes
4. Adjust skill templates if needed

## Quick Deployment

```bash
# 1. Install aieng-bot
uv sync  # or pip install aieng-bot

# 2. Set environment variables
export ANTHROPIC_API_KEY="your-key"
export GITHUB_TOKEN="your-token"

# 3. Test on a PR
aieng-bot fix --repo owner/repo --pr 123

# 4. (Optional) For automated workflows, add secrets to GitHub:
# Settings → Secrets → Actions → Add ANTHROPIC_API_KEY and ORG_ACCESS_TOKEN
```

## What Happens After Deployment

### First Day
- Discovery workflow runs at 00:00 UTC
- Scans all VectorInstitute repos
- Finds bot PRs (Dependabot and pre-commit-ci)
- Classifies failures with Claude Haiku 4.5
- Dispatches fix jobs for failing PRs
- Auto-merges passing PRs

### First Week
- Bot handles most bot PRs automatically
- Team sees reduced manual PR review load
- Fix success rate becomes visible on [Dashboard](https://platform.vectorinstitute.ai/aieng-bot)

## Monitoring

### Dashboard
View comprehensive analytics at [platform.vectorinstitute.ai/aieng-bot](https://platform.vectorinstitute.ai/aieng-bot):
- PR status tracking
- Agent execution traces
- Success rates and metrics

### CLI Commands
```bash
# Check recent runs
gh run list --workflow=discover-and-dispatch.yml --limit 10

# Check for failures
gh run list --workflow=discover-and-dispatch.yml --status failure --limit 5

# View specific run
gh run view RUN_ID --log
```

### Success Metrics
- Discovery workflow: 95%+ success rate
- Auto-merge: 90%+ of passing PRs merged
- Auto-fix: 50%+ of fixable issues resolved

## Adjustments

### Scan Frequency

Edit `.github/workflows/discover-and-dispatch.yml`:
```yaml
on:
  schedule:
    - cron: '0 0 * * *'    # Daily (default)
    - cron: '0 */12 * * *' # Every 12 hours
    - cron: '0 */6 * * *'  # Every 6 hours
```

### Exclude Repositories

Filter repos in workflow after getting the list:
```bash
REPOS=$(echo "$REPOS" | grep -v "repo-to-exclude")
```

### Adjust Fix Behavior

Edit skill templates in `.claude/skills/` to tune fix strategies.

## Rollback Plan

### Immediate Disable
```bash
gh workflow disable discover-and-dispatch.yml
```

Or via GitHub UI: Actions → Select workflow → "..." → Disable workflow

### Full Rollback
- Remove secrets from repository
- Disable workflows
- No cleanup needed in target repositories

## Cost Estimation

### Claude API
- Classification: Claude Haiku 4.5 (low cost)
- Fixing: Claude Sonnet 4.5 (moderate cost)
- Estimated: $5-20/month depending on volume

### GitHub
- Actions minutes: Free for public repos, included in plan for private
- API calls: Free within rate limits

## Team Communication

### Announcement Template
```markdown
## 🤖 aieng-bot

We've deployed aieng-bot to help manage PR maintenance.

**What it does:**
- Fixes CI failures (linting, tests, security, build)
- Resolves merge conflicts
- Auto-merges PRs when all checks pass
- Comments on PRs it processes

**How to use:**
- CLI: `aieng-bot fix --repo owner/repo --pr 123`
- Automated workflows handle bot PRs (Dependabot, pre-commit-ci)
- Report issues at github.com/VectorInstitute/aieng-bot
```

## Long-Term Maintenance

### Monthly
- Review bot effectiveness
- Update skills based on patterns
- Check API costs

### Quarterly
- Analyze metrics and trends
- Review for model updates
- Security and permissions audit

---

🤖 *aieng-bot - AI-powered PR maintenance by Vector Institute AI Engineering*
