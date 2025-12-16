# Testing Guide

## Test Environment Setup

1. **Fork a repository** or use a test repository
2. **Enable Dependabot**: Settings → Security → Dependabot
3. **Install workflows**: Copy `.github/workflows/` to test repo
4. **Add secrets**: Set `GEMINI_API_KEY`
5. **Enable auto-merge**: Settings → General → Pull Requests

## Test Cases

### Test Case 1: Auto-Merge Success
**Goal**: Verify bot auto-merges PRs when all checks pass

**Steps**:
1. Wait for or create Dependabot PR
2. Ensure all checks pass
3. Monitor workflow: `auto-merge-dependabot`

**Expected**:
- Bot approves PR with comment
- Auto-merge enabled
- PR merges automatically
- Success comment posted

### Test Case 2: Fix Test Failures
**Goal**: Verify bot fixes failing tests

**Test PR**: [aieng-template-mvp#17](https://github.com/VectorInstitute/aieng-template-mvp/pull/17)

**Steps**:
1. Trigger on PR with frontend-tests failing
2. Monitor workflow: `fix-failing-pr`
3. Check bot comments
4. Review pushed changes

**Expected**:
- Bot detects test failure
- Comments "Attempting to fix"
- Pushes fix commit
- Comments result

### Test Case 3: Fix Linting Issues
**Goal**: Verify bot fixes linting problems

**Setup**:
1. Create PR that introduces linting errors
2. Ensure linting checks fail

**Expected**:
- Bot identifies lint failures
- Runs auto-fixers (eslint --fix, prettier, black)
- Commits fixes
- Checks pass

### Test Case 4: Security Vulnerabilities
**Goal**: Verify bot updates vulnerable dependencies

**Setup**:
1. Dependabot PR with pip-audit failures
2. Security scan shows CVEs

**Expected**:
- Bot identifies vulnerable packages
- Updates to patched versions
- Updates requirements.txt
- Commits with CVE references

### Test Case 5: Build Failures
**Goal**: Verify bot fixes build errors

**Setup**:
1. PR with TypeScript compilation errors
2. Build check fails

**Expected**:
- Bot analyzes build logs
- Identifies type errors
- Updates type definitions
- Build passes

### Test Case 6: Manual Intervention Required
**Goal**: Verify bot correctly identifies unfixable issues

**Setup**:
1. PR with complex breaking changes
2. Multiple critical failures

**Expected**:
- Bot attempts fix
- Recognizes limitations
- Comments: "Could not automatically fix"
- Suggests manual review

## Manual Testing

### Trigger Workflows Manually

```bash
# Using GitHub CLI
gh workflow run auto-merge-dependabot.yml --repo VectorInstitute/your-repo

# Or via Actions tab:
# Actions → Select workflow → Run workflow
```

### Test Individual Components

**Test prompt loading**:
```bash
# Check prompt files exist and are valid markdown
find .github/prompts -name "*.md" -exec md_lint {} \;
```

**Test failure detection**:
```bash
# Simulate failure detection
gh pr view PR_NUMBER --json statusCheckRollup
```

**Test Gemini API**:
```bash
# Verify API key works
curl -H "Authorization: Bearer $GEMINI_API_KEY" \
  https://generativelanguage.googleapis.com/v1beta/models
```

## Integration Testing

### Test Across Multiple Repos

1. **Select diverse repos**:
   - Python project
   - JavaScript/TypeScript project
   - Mixed stack project

2. **Test different scenarios**:
   - Patch updates (x.y.Z)
   - Minor updates (x.Y.0)
   - Major updates (X.0.0)
   - Security updates
   - Multiple dependency updates

3. **Monitor for**:
   - False positives (incorrect merges)
   - False negatives (missed opportunities)
   - Failed fixes (bot breaks things)
   - API errors (Gemini failures)

## Rollback Testing

**Scenario**: Bot makes incorrect changes

**Steps**:
1. Create PR with intentional issues
2. Let bot attempt fix
3. Verify rollback mechanism
4. Check git history

**Expected**:
- Commits are atomic
- Easy to revert
- No data loss
- Clear commit messages

## Performance Testing

### Metrics to Track

```bash
# Average time to auto-merge
# Average time to fix
# Success rate (fixes / attempts)
# API call count
# Cost per fix (Gemini API)
```

### Load Testing

**Scenario**: Multiple PRs simultaneously

**Setup**:
1. Create 10+ Dependabot PRs
2. Some passing, some failing
3. Monitor workflow queue

**Expected**:
- All PRs processed
- No race conditions
- No duplicate fixes
- Workflows don't block each other

## Debugging Tests

### Check Workflow Logs

```bash
# Get latest run for a workflow
gh run list --workflow=auto-merge-dependabot.yml --limit 1

# View logs
gh run view RUN_ID --log

# Download logs
gh run download RUN_ID
```

### Common Issues

| Issue | Debug Steps |
|-------|-------------|
| Workflow doesn't trigger | Check event triggers, PR author |
| API errors | Verify secrets, check quotas |
| Fixes don't work | Review prompt, check model |
| Can't push | Check permissions, branch protection |

## Test Documentation

Record test results:
```markdown
## Test Run: YYYY-MM-DD

**Environment**: [staging/production/test-repo]
**Test Cases**: [list]
**Results**: [pass/fail counts]
**Issues Found**: [list]
**Actions Taken**: [fixes applied]
```

## Continuous Testing

**Schedule regular tests**:
- Weekly: Run test suite
- Monthly: Load testing
- Quarterly: Full integration test
- After changes: Regression testing

## Success Criteria

✅ Auto-merge: 95%+ success rate
✅ Auto-fix: 70%+ success rate
✅ No false positives: 0 incorrect merges
✅ Fast execution: <5min average
✅ Cost effective: <$1 per fix average

---

🤖 *AI Engineering Maintenance Bot - Maintaining Vector Institute Repositories built by AI Engineering*
