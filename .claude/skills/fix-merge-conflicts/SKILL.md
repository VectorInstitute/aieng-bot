---
name: fix-merge-conflicts
description: Resolve git merge conflicts in dependency files, source code, and configuration. Use when merge conflicts are detected during rebase.
allowed-tools: Read, Edit, Bash, Glob, Grep
---

# Fix Merge Conflicts

Provides domain expertise for resolving merge conflicts. This skill fixes files only - the main loop handles git operations (commit, push, CI, merge).

## Scope

**This skill DOES:**
- Resolve conflict markers in files
- Regenerate lock files
- Stage resolved files for the rebase to continue

**This skill does NOT do (main loop handles these):**
- ❌ Commit changes
- ❌ Push to remote
- ❌ Wait for CI
- ❌ Merge the PR

## Process

### 1. Identify Conflicts
```bash
git status
git diff --name-only --diff-filter=U
```

### 2. Resolution Strategy by File Type

**Dependency Files (package.json, pyproject.toml, requirements.txt)**
- Prefer newer versions
- Keep additions from both sides
- Maintain consistent formatting

Example:
```
<<<<<<< HEAD
"dep-a": "^2.0.0",
"dep-b": "^1.5.0"
=======
"dep-a": "^1.9.0",
"dep-c": "^3.0.0"
>>>>>>> PR

RESOLVE TO:
"dep-a": "^2.0.0",  // Newer version
"dep-b": "^1.5.0",  // From base
"dep-c": "^3.0.0"   // From PR
```

**Lock Files (uv.lock, package-lock.json)**
- DON'T manually edit lock files
- Delete and regenerate:
```bash
# For Python (uv)
rm uv.lock
unset VIRTUAL_ENV
uv lock

# For npm
rm package-lock.json
npm install
```

**Source Code**
- Preserve functionality from both sides when possible
- Base branch wins for different implementations (more recent)
- Combine both additions if compatible
- Follow base formatting

**Configuration Files (.yml, .toml, .json configs)**
- Merge both sets of changes logically
- Preserve workflow improvements
- Maintain proper syntax

**Documentation**
- Combine both updates
- Keep chronological order for changelogs
- Preserve both feature descriptions

### 3. Resolution Steps
For each conflicted file:
1. Read entire file for context
2. Locate conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
3. Analyze both versions
4. Apply resolution strategy for file type
5. Edit file to remove ALL markers
6. Verify syntax is valid

### 4. Finalize Resolution
```bash
# Stage resolved files (NOT bot files)
git add <resolved-files>

# Verify no conflict markers remain
git diff --check

# Continue the rebase
git rebase --continue
```

**Files to NEVER stage:**
- `.claude/` directory
- `.pr-context.json`
- `.failure-logs.txt`

## Safety Rules
- ❌ Don't leave conflict markers in any file
- ❌ Don't choose older versions over newer
- ❌ Don't manually edit lock files (regenerate them)
- ❌ Don't discard additions from either side without reason
- ✅ Verify syntax after resolution
- ✅ Regenerate lock files using package manager
- ✅ Test that resolved files are valid
