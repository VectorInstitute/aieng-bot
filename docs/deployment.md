# Deployment Guide

## Overview

Deploying the AI Engineering Maintenance Bot is simple - it runs from ONE central repository and requires NO installation in individual repositories.

## Deployment Checklist

### Phase 1: Initial Setup (30 minutes)

- [ ] **1.1**: Create Anthropic API key
- [ ] **1.2**: Create GitHub PAT with org-wide access
- [ ] **1.3**: Add secrets to this repository
  - `ANTHROPIC_API_KEY`
  - `ORG_ACCESS_TOKEN`
- [ ] **1.4**: Enable GitHub Actions
- [ ] **1.5**: Verify workflows appear in Actions tab

### Phase 2: Testing (1-2 hours)

- [ ] **2.1**: Manual test run of monitor workflow
  ```bash
  gh workflow run monitor-org-dependabot.yml \
    --repo VectorInstitute/aieng-bot-maintain
  ```
- [ ] **2.2**: Test fix workflow on specific PR
  ```bash
  gh workflow run fix-remote-pr.yml \
    --repo VectorInstitute/aieng-bot-maintain \
    --field target_repo="VectorInstitute/aieng-template-mvp" \
    --field pr_number="17"
  ```
- [ ] **2.3**: Verify bot comments appear on test PR
- [ ] **2.4**: Check workflow logs for errors
- [ ] **2.5**: Confirm bot can access org repos

### Phase 3: Limited Monitoring (Week 1-2)

- [ ] **3.1**: Enable scheduled runs (automatic every 6 hours)
- [ ] **3.2**: Monitor for 2-3 days
- [ ] **3.3**: Check PRs the bot processes
- [ ] **3.4**: Verify auto-merge works correctly
- [ ] **3.5**: Review any fixes the bot applies
- [ ] **3.6**: Adjust prompt templates if needed

### Phase 4: Full Production (Week 3+)

- [ ] **4.1**: Confirm bot stability
- [ ] **4.2**: Enable auto-merge in more repos
- [ ] **4.3**: Announce to VectorInstitute team
- [ ] **4.4**: Document any customizations made
- [ ] **4.5**: Set up monitoring dashboard

## Quick Deployment

For experienced admins who just want to get it running:

```bash
# 1. Add secrets via GitHub UI
# Settings → Secrets → Actions → New secret
# - ANTHROPIC_API_KEY
# - ORG_ACCESS_TOKEN

# 2. Enable workflows
# Actions tab → Enable workflows

# 3. Test
gh workflow run monitor-org-dependabot.yml --repo VectorInstitute/aieng-bot-maintain

# 4. Monitor
# Check Actions tab for runs every 6 hours
```

## What Happens After Deployment

### First 6 Hours
- Monitor workflow runs automatically
- Scans all VectorInstitute repos
- Finds any open Dependabot PRs
- Processes passing PRs (auto-merge)
- Triggers fixes for failing PRs
- Bot comments appear on processed PRs
- Auto-merges happen for passing PRs
- Fix attempts made on failing PRs

### First Day
- 4 scan cycles (every 6 hours)
- All active Dependabot PRs processed
- Pattern of bot behavior visible
- Any issues surface quickly

### First Week
- Bot handles most Dependabot PRs automatically
- Team sees reduced manual PR review load
- Fix success rate becomes clear
- Prompt adjustments may be needed

## Monitoring After Deployment

### Daily Checks (First 2 Weeks)

Monitor these metrics:
```bash
# Check recent runs
gh run list --workflow=monitor-org-dependabot.yml --limit 10

# Check for failures
gh run list --workflow=monitor-org-dependabot.yml --status failure --limit 5

# View specific run
gh run view RUN_ID --log
```

Track:
- PRs found per run
- PRs auto-merged
- PRs fixed successfully
- Any workflow failures
- API errors or rate limits

### Weekly Review

Review bot activity:
1. **Actions tab**: Check run success rate
2. **Across org repos**: Find PRs with bot comments
3. **Merged PRs**: Verify quality of auto-merged changes
4. **Fixed PRs**: Check if fixes worked correctly
5. **Metrics**: Count successes vs failures

### Success Metrics

Target metrics after 2 weeks:
- ✅ Monitor workflow: 95%+ success rate
- ✅ Auto-merge: 90%+ of passing PRs merged
- ✅ Auto-fix: 50%+ of fixable issues resolved
- ✅ False positives: 0 (no incorrect merges)
- ✅ Team feedback: Positive

## Common Post-Deployment Adjustments

### Adjust Scan Frequency

If you want more or less frequent scanning:

```yaml
# .github/workflows/monitor-org-dependabot.yml
on:
  schedule:
    - cron: '0 */12 * * *'  # Every 12 hours (less frequent)
    # or
    - cron: '0 */3 * * *'   # Every 3 hours (more frequent)
```

### Exclude Specific Repositories

If certain repos need manual review:

```bash
# In monitor-org-dependabot.yml, after getting REPOS
REPOS=$(echo "$REPOS" | grep -v "critical-production-repo")
REPOS=$(echo "$REPOS" | grep -v "experimental-repo")
```

### Adjust Fix Aggressiveness

If bot makes too many/few fix attempts:

Edit `.github/prompts/` templates to be more/less aggressive in fixes.

### Fine-Tune Merge Criteria

If auto-merging incorrectly:

```bash
# In monitor-org-dependabot.yml, adjust check logic
# Add filters for specific check names or PR titles
```

## Rollback Plan

If something goes wrong:

### Immediate Disable (30 seconds)

```bash
# Disable scheduled runs
gh workflow disable monitor-org-dependabot.yml \
  --repo VectorInstitute/aieng-bot-maintain
```

Or via GitHub UI:
1. Actions → Monitor Organization Dependabot PRs
2. Click "..." → Disable workflow

### Investigation (While Disabled)

1. Check recent workflow runs for errors
2. Review PRs the bot touched recently
3. Check for incorrect merges or fixes
4. Identify the issue

### Fix and Re-enable

1. Make necessary corrections (prompts, logic, secrets)
2. Test manually first
3. Re-enable workflow:
   ```bash
   gh workflow enable monitor-org-dependabot.yml
   ```

### Full Rollback (If Needed)

The bot makes no permanent infrastructure changes:
- Remove secrets from repository
- Disable workflows
- No cleanup needed in target repositories
- Bot comments remain (harmless documentation)

## Cost Estimation

### Claude API Costs

Assuming:
- 10 Dependabot PRs/day across org
- 50% need fixes (5/day)
- ~2000 tokens per fix request
- Claude Sonnet: ~$0.001 per 1K tokens

**Estimated cost**: $0.01-0.05 per day = **$0.30-1.50 per month**

### GitHub API Costs

- Organization scanning: Free (read operations)
- PR operations: Free (within rate limits)
- Actions minutes: Free for public repos, included in plan for private

**Total estimated cost**: **<$2/month**

## Team Communication

### Announcement Template

```markdown
## 🤖 New: AI Engineering Maintenance Bot

We've deployed an automated bot to help manage Dependabot PRs across all VectorInstitute repositories.

**What it does:**
- Automatically merges Dependabot PRs when all checks pass
- Attempts to fix common issues (linting, tests, security) in failing PRs
- Leaves comments on PRs it processes

**What you need to do:**
- Nothing! The bot works automatically
- You can still manually review and merge if you prefer
- Report any issues to the AI Engineering team

**More info:** https://github.com/VectorInstitute/aieng-bot-maintain
```

Post in:
- Organization Slack/Teams channel
- Team meetings
- Internal wiki/docs

## Long-Term Maintenance

### Monthly Tasks
- Review bot effectiveness
- Update prompts based on patterns
- Check API costs vs budget
- Rotate tokens if needed

### Quarterly Tasks
- Analyze metrics and trends
- Consider feature enhancements
- Update to new Gemini models
- Review security and permissions

### Annual Tasks
- Full security audit
- Architecture review
- Cost-benefit analysis
- Team satisfaction survey

## Scaling Considerations

### Current Capacity
- Handles 100s of repos
- Processes unlimited PRs
- Limited by: GitHub API rate limits, Claude API quota

### If Scaling Needed
- Increase Claude API quota
- Use GitHub App instead of PAT (higher rate limits)
- Shard by repository (multiple bot instances)
- Cache PR status to reduce API calls

## Support and Updates

### Getting Updates
Watch this repository for:
- Bug fixes
- New features
- Improved prompts
- Gemini model updates

### Contributing Improvements
Submit PRs with:
- Better prompt templates
- Enhanced error handling
- New failure type detection
- Improved logging

---

🤖 *AI Engineering Maintenance Bot - Maintaining Vector Institute Repositories built by AI Engineering*
