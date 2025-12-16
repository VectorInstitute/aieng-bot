# aieng-bot-maintain Documentation

Comprehensive documentation for the AI Engineering Maintenance Bot - an automated system that manages Dependabot PRs across all Vector Institute repositories.

## Getting Started

- **[Setup Guide](setup.md)** - Complete setup instructions including API keys, tokens, and configuration
- **[Deployment Guide](deployment.md)** - Step-by-step deployment process and monitoring strategies
- **[Testing Guide](testing.md)** - Test cases, validation procedures, and debugging

## Quick Links

- [Main Repository](../) - Return to repository root
- [Workflow Files](../.github/workflows/) - GitHub Actions workflows
- [Prompt Templates](../.github/prompts/) - AI prompt templates for different failure types

## Overview

The bot operates from a single centralized repository and requires no installation in individual repositories. It:

- Monitors all VectorInstitute repositories every 6 hours
- Auto-merges Dependabot PRs when all checks pass
- Automatically fixes common issues using Claude Agent SDK
- Posts transparent status updates on PRs

## Key Features

### Organization-Wide Monitoring
Scans all repositories in the VectorInstitute organization for open Dependabot PRs and processes them automatically.

### Intelligent Auto-Merge
Analyzes PR status checks and automatically approves and merges PRs when all tests pass.

### AI-Powered Auto-Fix
Uses Claude Agent SDK to analyze failures and directly modify code to fix:
- Test failures from dependency updates
- Linting and formatting issues
- Security audit failures
- Build configuration problems

### Centralized Operation
All logic runs from this single repository - target repositories need only:
- Dependabot enabled
- Auto-merge enabled (optional but recommended)

## Architecture

```
┌───────────────────────────┐
│  aieng-bot-maintain       │
│  (This Repository)        │
│                           │
│  Workflows:               │
│  • monitor (every 6hrs)   │
│  • fix (on-demand)        │
└────────────┬──────────────┘
             │
             │ Manages
             ▼
┌────────────────────────────┐
│  VectorInstitute Org Repos │
│                            │
│  Finds & processes         │
│  Dependabot PRs            │
└────────────────────────────┘
```

## Configuration

### Required Secrets
- `ANTHROPIC_API_KEY` - API access for Claude (get from [Anthropic Console](https://console.anthropic.com/settings/keys))
- `ORG_ACCESS_TOKEN` - GitHub PAT with org-wide write permissions

### Workflows
- `monitor-org-dependabot.yml` - Scheduled workflow that scans organization
- `fix-remote-pr.yml` - On-demand workflow triggered for failing PRs

### Customization
- Edit `.github/prompts/*.md` files to customize fix strategies
- Adjust cron schedule in monitor workflow for different frequencies
- Modify failure detection logic in workflow files

## Common Tasks

### Manual Testing
```bash
# Test monitoring workflow
gh workflow run monitor-org-dependabot.yml

# Test fix on specific PR
gh workflow run fix-remote-pr.yml \
  --field target_repo="VectorInstitute/aieng-template-mvp" \
  --field pr_number="17"
```

### Monitoring Bot Activity
```bash
# View recent runs
gh run list --workflow=monitor-org-dependabot.yml --limit 5

# View specific run logs
gh run view RUN_ID --log
```

### Debugging Issues
Check:
- Actions tab for workflow execution logs
- PR comments for bot status updates
- Repository secrets are properly set
- Token permissions are correct

## Support

For issues, questions, or contributions:
- Open an issue in this repository
- Check workflow logs for error details
- Review PR comments for bot activity
- Contact AI Engineering team for urgent issues

---

🤖 *AI Engineering Maintenance Bot - Maintaining Vector Institute Repositories built by AI Engineering*
