# AI Engineering Maintenance Bot - Setup Guide

## Overview

This centralized bot operates from THIS repository and manages Dependabot PRs across ALL VectorInstitute repositories. No installation needed in individual repos.

## Prerequisites

- [ ] Admin access to VectorInstitute organization
- [ ] Ability to create organization secrets
- [ ] Anthropic API key
- [ ] GitHub Personal Access Token with org-wide permissions

## Setup Steps

### 1. Create Claude API Key

1. Go to [Anthropic Console](https://console.anthropic.com/settings/keys)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key (starts with `AIza...`)
5. Keep it secure - you'll add it as a secret

### 2. Create GitHub Personal Access Token

**Option A: Fine-grained Token (Recommended)**

1. Go to GitHub Settings → Developer settings → Personal access tokens → [Fine-grained tokens](https://github.com/settings/tokens?type=beta)
2. Click "Generate new token"
3. Configure:
   - **Token name**: `aieng-bot-maintain-org-access`
   - **Expiration**: 1 year (or longer)
   - **Resource owner**: VectorInstitute
   - **Repository access**: All repositories
   - **Permissions**:
     - Repository permissions:
       - `contents`: Read and write
       - `pull_requests`: Read and write
       - `issues`: Read and write
       - `metadata`: Read-only (automatic)
     - Organization permissions:
       - `members`: Read-only (for org scanning)
4. Click "Generate token"
5. Copy the token (starts with `github_pat_...`)

**Option B: Classic Token (Alternative)**

1. Go to GitHub Settings → Developer settings → [Personal access tokens (classic)](https://github.com/settings/tokens)
2. Click "Generate new token (classic)"
3. Configure:
   - **Note**: `aieng-bot-maintain-org-access`
   - **Expiration**: 1 year (or longer)
   - **Scopes**: Select:
     - `repo` (Full control of private repositories)
     - `workflow` (Update GitHub Action workflows)
     - `read:org` (Read org and team membership)
4. Click "Generate token"
5. Copy the token (starts with `ghp_...`)

### 3. Add Secrets to This Repository

1. Go to this repository: `VectorInstitute/aieng-bot-maintain`
2. Navigate to Settings → Secrets and variables → Actions
3. Click "New repository secret"

**Add ANTHROPIC_API_KEY**:
- Name: `ANTHROPIC_API_KEY`
- Secret: [Paste your Anthropic API key]
- Click "Add secret"

**Add ORG_ACCESS_TOKEN**:
- Name: `ORG_ACCESS_TOKEN`
- Secret: [Paste your GitHub PAT]
- Click "Add secret"

### 4. Enable GitHub Actions

1. In this repository, go to Actions tab
2. If actions are disabled, click "I understand my workflows, go ahead and enable them"
3. Verify workflows appear:
   - Monitor Organization Dependabot PRs
   - Fix Remote Repository PR

### 5. Enable Auto-Merge in Target Repositories (Optional)

For best results, enable auto-merge in repos you want the bot to manage:

1. Go to each target repository
2. Settings → General → Pull Requests
3. Check ☑ "Allow auto-merge"
4. Save changes

**Note**: This can be done later as needed. The bot will still approve PRs even if auto-merge is not enabled.

### 6. Test the Setup

#### Manual Test Run

1. Go to Actions tab in this repository
2. Select "Monitor Organization Dependabot PRs"
3. Click "Run workflow"
4. Click "Run workflow" button (leave fields empty for org-wide scan)
5. Wait for completion (usually 1-2 minutes)
6. Check the workflow run summary for results

#### Test with Specific PR

Test against [aieng-template-mvp#17](https://github.com/VectorInstitute/aieng-template-mvp/pull/17):

```bash
gh workflow run fix-remote-pr.yml \
  --repo VectorInstitute/aieng-bot-maintain \
  --field target_repo="VectorInstitute/aieng-template-mvp" \
  --field pr_number="17"
```

Or via GitHub UI:
1. Actions → Fix Remote Repository PR
2. Run workflow
3. Enter:
   - target_repo: `VectorInstitute/aieng-template-mvp`
   - pr_number: `17`
4. Click "Run workflow"

### 7. Verify Bot Operation

After setup, the bot should:

✅ Run automatically every 6 hours
✅ Scan all VectorInstitute repositories
✅ Find open Dependabot PRs
✅ Auto-merge PRs with passing checks
✅ Trigger fixes for PRs with failures
✅ Leave comments on PRs it processes

Check the Actions tab for workflow runs and PR comments for bot activity.

## Configuration

### Adjust Monitoring Frequency

Edit `.github/workflows/monitor-org-dependabot.yml`:

```yaml
on:
  schedule:
    - cron: '0 */6 * * *'   # Every 6 hours (current default)
    # Change to:
    # - cron: '0 */3 * * *'   # Every 3 hours
    # - cron: '0 */12 * * *'  # Every 12 hours
    # - cron: '0 0 * * *'     # Once daily at midnight
```

### Customize Fix Prompts

Edit prompt templates in `.github/prompts/`:
- `fix-test-failures.md`
- `fix-lint-failures.md`
- `fix-security-audit.md`
- `fix-build-failures.md`

Add repository-specific context, commands, or strategies.

### Filter Repositories

To exclude certain repos from monitoring, edit `monitor-org-dependabot.yml`:

```bash
# After getting repos list
REPOS=$(echo "$REPOS" | grep -v "repo-to-exclude")
REPOS=$(echo "$REPOS" | grep -v "another-repo-to-exclude")
```

### Change Gemini Model

Edit `.github/workflows/fix-remote-pr.yml`:

```yaml
- name: Setup Gemini CLI
  uses: google-github-actions/run-gemini-cli@v1
  with:
    gemini_model: 'gemini-3-pro-preview'  # Current
    # Options:
    #   gemini-2.0-flash-exp  (faster, lower cost)
    #   gemini-1.5-pro        (more tested, stable)
```

## Security Considerations

### Token Permissions

The `ORG_ACCESS_TOKEN` has broad access. Best practices:
- ✅ Use fine-grained token when possible
- ✅ Set token expiration (rotate annually)
- ✅ Monitor token usage in GitHub audit log
- ✅ Revoke and rotate if compromised
- ❌ Never commit tokens to repository
- ❌ Never share tokens via insecure channels

### API Key Protection

The `ANTHROPIC_API_KEY` provides AI access:
- ✅ Monitor API usage and costs
- ✅ Set usage quotas in Google Cloud
- ✅ Rotate key periodically
- ✅ Use separate key per environment (if needed)

### Bot Actions Audit

Regularly review bot actions:
- Check PR comments for inappropriate changes
- Review merged PRs for correctness
- Monitor for false positives
- Adjust prompts if bot makes mistakes

## Troubleshooting

### Bot Not Finding PRs

**Check**: `ORG_ACCESS_TOKEN` permissions
```bash
# Test token access
gh api user -H "Authorization: token $ORG_ACCESS_TOKEN"

# Test org access
gh api orgs/VectorInstitute/repos -H "Authorization: token $ORG_ACCESS_TOKEN"
```

### Bot Can't Merge PRs

**Possible causes**:
- Auto-merge not enabled in target repo
- Branch protection rules blocking
- Required reviews not satisfied
- Token lacks permissions

**Solution**: Check target repo settings and ensure token has `contents: write`

### Bot Can't Push Fixes

**Check**: Token permissions and branch protection
```bash
# Test write access to a repo
gh api repos/VectorInstitute/TEST_REPO/collaborators/USERNAME/permission
```

**Solution**: Ensure token has write access and branch protection allows bot pushes

### Claude API Errors

**Common issues**:
- Invalid API key
- Quota exceeded
- Model not available
- Request too large

**Check quota**: Visit [Anthropic Console](https://console.anthropic.com/settings/keys)

**Solution**: Verify key, check quota, consider upgrading plan

### Workflow Not Running

**Check**:
1. Actions enabled in repository
2. Secrets set correctly
3. Workflow file syntax valid
4. Cron schedule correct (uses UTC)

```bash
# Test workflow manually
gh workflow run monitor-org-dependabot.yml
```

## Maintenance

### Weekly Tasks
- [ ] Review workflow runs for errors
- [ ] Check PR comments for bot activity
- [ ] Monitor API costs (Gemini and GitHub)
- [ ] Verify bot is finding and processing PRs

### Monthly Tasks
- [ ] Review merged PRs for quality
- [ ] Update prompt templates based on patterns
- [ ] Check for new Gemini models or features
- [ ] Audit token usage and permissions

### Quarterly Tasks
- [ ] Rotate tokens (if policy requires)
- [ ] Review and update documentation
- [ ] Analyze bot effectiveness metrics
- [ ] Consider architecture improvements

## Support

### Getting Help

- **GitHub Issues**: Open issue in this repository
- **Workflow Logs**: Actions tab → Select run → View logs
- **AI Engineering Team**: Contact for urgent issues

### Reporting Problems

When reporting issues, include:
1. Workflow run URL
2. Target repository and PR number
3. Expected vs actual behavior
4. Relevant workflow logs
5. Error messages

---

🤖 *AI Engineering Maintenance Bot - Maintaining Vector Institute Repositories built by AI Engineering*
