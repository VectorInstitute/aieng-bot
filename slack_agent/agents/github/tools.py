"""Tool definitions and execution for the GitHub QA agent.

All tools are read-only and pinned to one organization by the client;
results are trimmed to what the model needs so raw API payloads never
bloat the context window.
"""

import base64
import json
from collections.abc import Callable
from typing import Any

from anthropic.types import ToolParam

from .client import GitHubClient

LIST_REPOS_TOOL: ToolParam = {
    "name": "list_repos",
    "description": (
        "List repositories in the Vector Institute GitHub organization, "
        "most recently pushed first. "
        "Use this to discover repositories or check recent activity."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Number of repositories to return (1-100, default 30).",
                "default": 30,
            },
        },
        "required": [],
    },
}

GET_REPO_TOOL: ToolParam = {
    "name": "get_repo",
    "description": (
        "Fetch one repository's metadata: description, primary language, "
        "default branch, topics, and activity. "
        "Use the bare repository name, without the organization prefix."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. aieng-bot.",
            },
        },
        "required": ["repo"],
    },
}

SEARCH_CODE_TOOL: ToolParam = {
    "name": "search_code",
    "description": (
        "Search code across all repositories in the Vector Institute GitHub "
        "organization. "
        "Returns matching file paths; call get_file to read the contents. "
        "Supports GitHub code-search qualifiers like filename:, path:, "
        "language:, and repo-narrowing is automatic."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search terms, e.g. a function name or config key.",
            },
            "limit": {
                "type": "integer",
                "description": "Number of results to return (1-30, default 10).",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}

GET_FILE_TOOL: ToolParam = {
    "name": "get_file",
    "description": (
        "Read one file from a repository (README, source file, config) at "
        "an optional branch, tag, or commit. "
        "Returns the decoded text content and the file's GitHub URL."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. aieng-bot.",
            },
            "path": {
                "type": "string",
                "description": "File path within the repository, e.g. README.md.",
            },
            "ref": {
                "type": "string",
                "description": (
                    "Branch, tag, or commit SHA (omit for the default branch)."
                ),
            },
        },
        "required": ["repo", "path"],
    },
}

LIST_PULL_REQUESTS_TOOL: ToolParam = {
    "name": "list_pull_requests",
    "description": (
        "List a repository's pull requests, most recently updated first. "
        "Use state 'open' (default), 'closed', or 'all'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. aieng-bot.",
            },
            "state": {
                "type": "string",
                "enum": ["open", "closed", "all"],
                "description": "Which pull requests to list (default open).",
            },
            "limit": {
                "type": "integer",
                "description": "Number of results to return (1-50, default 20).",
                "default": 20,
            },
        },
        "required": ["repo"],
    },
}

GET_PULL_REQUEST_TOOL: ToolParam = {
    "name": "get_pull_request",
    "description": (
        "Fetch one pull request in full: description, branches, merge "
        "state, changed files, and recent discussion comments."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. aieng-bot.",
            },
            "number": {
                "type": "integer",
                "description": "Pull request number.",
            },
        },
        "required": ["repo", "number"],
    },
}

LIST_ISSUES_TOOL: ToolParam = {
    "name": "list_issues",
    "description": (
        "List a repository's issues (pull requests excluded), most "
        "recently updated first. "
        "Use state 'open' (default), 'closed', or 'all'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. aieng-bot.",
            },
            "state": {
                "type": "string",
                "enum": ["open", "closed", "all"],
                "description": "Which issues to list (default open).",
            },
            "limit": {
                "type": "integer",
                "description": "Number of results to return (1-50, default 20).",
                "default": 20,
            },
        },
        "required": ["repo"],
    },
}

GET_ISSUE_TOOL: ToolParam = {
    "name": "get_issue",
    "description": (
        "Fetch one issue in full: description, labels, state, and recent "
        "discussion comments."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. aieng-bot.",
            },
            "number": {
                "type": "integer",
                "description": "Issue number.",
            },
        },
        "required": ["repo", "number"],
    },
}

GET_CI_STATUS_TOOL: ToolParam = {
    "name": "get_ci_status",
    "description": (
        "Fetch CI check results for a branch, tag, or commit of a "
        "repository. "
        "Returns each check's name, status, and conclusion plus a "
        "pass/fail summary. Defaults to the repository's default branch."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "Repository name, e.g. aieng-bot.",
            },
            "ref": {
                "type": "string",
                "description": (
                    "Branch, tag, or commit SHA (omit for the default branch). "
                    "For a pull request, use its head branch."
                ),
            },
        },
        "required": ["repo"],
    },
}

ALL_TOOLS: list[ToolParam] = [
    LIST_REPOS_TOOL,
    GET_REPO_TOOL,
    SEARCH_CODE_TOOL,
    GET_FILE_TOOL,
    LIST_PULL_REQUESTS_TOOL,
    GET_PULL_REQUEST_TOOL,
    LIST_ISSUES_TOOL,
    GET_ISSUE_TOOL,
    GET_CI_STATUS_TOOL,
]

GITHUB_TOOL_NAMES = frozenset(str(t["name"]) for t in ALL_TOOLS)

# Access level per tool, consumed by the system-prompt capability
# manifest and the authorization policy. Everything here is read-only;
# when write tools land they must be declared "write" to be gated.
TOOL_ACCESS: dict[str, str] = dict.fromkeys(GITHUB_TOOL_NAMES, "read")

# Payload trimming limits: keep tool results informative but bounded.
_MAX_FILE_CHARS = 40_000
_MAX_BODY_CHARS = 4_000
_MAX_COMMENT_CHARS = 1_500
_MAX_COMMENTS = 10
_MAX_PR_FILES = 50


def _truncate(text: str, limit: int) -> str:
    """Cut *text* at *limit* characters with an explicit marker."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated at {limit} characters]"


def _user_login(item: dict[str, Any]) -> str:
    """Return the author login of an API item, empty if absent."""
    user = item.get("user") or {}
    return str(user.get("login", ""))


def _comment_summaries(comments: list[Any]) -> list[dict[str, Any]]:
    """Condense discussion comments to author + trimmed body."""
    return [
        {
            "author": _user_login(c),
            "created_at": c.get("created_at", ""),
            "body": _truncate(str(c.get("body") or ""), _MAX_COMMENT_CHARS),
        }
        for c in comments[-_MAX_COMMENTS:]
        if isinstance(c, dict)
    ]


def _pr_summary(pr: dict[str, Any]) -> dict[str, Any]:
    """Condense a pull request to its listing fields."""
    return {
        "number": pr.get("number"),
        "title": pr.get("title"),
        "author": _user_login(pr),
        "state": pr.get("state"),
        "draft": pr.get("draft", False),
        "updated_at": pr.get("updated_at"),
        "url": pr.get("html_url", ""),
    }


def _issue_summary(issue: dict[str, Any]) -> dict[str, Any]:
    """Condense an issue to its listing fields."""
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "author": _user_login(issue),
        "state": issue.get("state"),
        "labels": [
            str(label.get("name", ""))
            for label in issue.get("labels", [])
            if isinstance(label, dict)
        ],
        "comment_count": issue.get("comments"),
        "updated_at": issue.get("updated_at"),
        "url": issue.get("html_url", ""),
    }


def _exec_list_repos(tool_input: dict[str, Any], client: GitHubClient) -> str:
    """List the org's repositories, trimmed to listing fields."""
    limit = max(1, min(int(tool_input.get("limit", 30)), 100))
    repos = client.list_repos(limit=limit)
    return json.dumps(
        [
            {
                "name": r.get("name"),
                "description": r.get("description"),
                "language": r.get("language"),
                "archived": r.get("archived", False),
                "pushed_at": r.get("pushed_at"),
                "url": r.get("html_url", ""),
            }
            for r in repos
            if isinstance(r, dict)
        ],
        indent=2,
    )


def _exec_get_repo(tool_input: dict[str, Any], client: GitHubClient) -> str:
    """Fetch one repository's metadata, trimmed."""
    raw = client.get_repo(str(tool_input["repo"]))
    return json.dumps(
        {
            "name": raw.get("name"),
            "description": raw.get("description"),
            "language": raw.get("language"),
            "default_branch": raw.get("default_branch"),
            "topics": raw.get("topics", []),
            "visibility": raw.get("visibility"),
            "archived": raw.get("archived", False),
            "open_issues_count": raw.get("open_issues_count"),
            "pushed_at": raw.get("pushed_at"),
            "url": raw.get("html_url", ""),
        },
        indent=2,
    )


def _exec_search_code(tool_input: dict[str, Any], client: GitHubClient) -> str:
    """Search org code; return matching paths for get_file follow-ups."""
    limit = max(1, min(int(tool_input.get("limit", 10)), 30))
    raw = client.search_code(str(tool_input["query"]), limit=limit)
    items = raw.get("items", []) if isinstance(raw, dict) else []
    return json.dumps(
        {
            "total": raw.get("total_count", 0),
            "results": [
                {
                    "repo": (item.get("repository") or {}).get("name", ""),
                    "path": item.get("path", ""),
                    "url": item.get("html_url", ""),
                }
                for item in items
                if isinstance(item, dict)
            ],
        },
        indent=2,
    )


def _exec_get_file(tool_input: dict[str, Any], client: GitHubClient) -> str:
    """Read one file, base64-decoded and truncated; directories list entries."""
    ref = str(tool_input["ref"]) if tool_input.get("ref") else None
    raw = client.get_file(str(tool_input["repo"]), str(tool_input["path"]), ref=ref)
    if isinstance(raw, list):
        entries = [e.get("path", "") for e in raw if isinstance(e, dict)]
        return json.dumps({"note": "path is a directory", "entries": entries}, indent=2)
    try:
        content = base64.b64decode(str(raw.get("content", ""))).decode(
            "utf-8", errors="replace"
        )
    except (ValueError, TypeError):
        return "Error: file content is not text (binary file?)"
    return json.dumps(
        {
            "name": raw.get("name"),
            "path": raw.get("path"),
            "url": raw.get("html_url", ""),
            "content": _truncate(content, _MAX_FILE_CHARS),
        },
        indent=2,
    )


def _exec_list_pull_requests(tool_input: dict[str, Any], client: GitHubClient) -> str:
    """List a repo's pull requests, trimmed to listing fields."""
    limit = max(1, min(int(tool_input.get("limit", 20)), 50))
    state = str(tool_input.get("state", "open"))
    prs = client.list_pull_requests(str(tool_input["repo"]), state=state, limit=limit)
    return json.dumps([_pr_summary(pr) for pr in prs if isinstance(pr, dict)], indent=2)


def _exec_get_pull_request(tool_input: dict[str, Any], client: GitHubClient) -> str:
    """Fetch one PR with its changed files and recent discussion."""
    repo = str(tool_input["repo"])
    number = int(tool_input["number"])
    pr = client.get_pull_request(repo, number)
    files = client.list_pull_request_files(repo, number, limit=_MAX_PR_FILES)
    comments = client.list_issue_comments(repo, number)
    result = _pr_summary(pr)
    result.update(
        {
            "body": _truncate(str(pr.get("body") or ""), _MAX_BODY_CHARS),
            "base": (pr.get("base") or {}).get("ref", ""),
            "head": (pr.get("head") or {}).get("ref", ""),
            "merged": pr.get("merged", False),
            "mergeable_state": pr.get("mergeable_state"),
            "additions": pr.get("additions"),
            "deletions": pr.get("deletions"),
            "changed_files": pr.get("changed_files"),
            "files": [
                {"path": f.get("filename", ""), "status": f.get("status", "")}
                for f in files
                if isinstance(f, dict)
            ],
            "comments": _comment_summaries(
                comments if isinstance(comments, list) else []
            ),
        }
    )
    return json.dumps(result, indent=2)


def _exec_list_issues(tool_input: dict[str, Any], client: GitHubClient) -> str:
    """List a repo's true issues (the API interleaves PRs; drop them)."""
    limit = max(1, min(int(tool_input.get("limit", 20)), 50))
    state = str(tool_input.get("state", "open"))
    issues = client.list_issues(str(tool_input["repo"]), state=state, limit=limit)
    return json.dumps(
        [
            _issue_summary(issue)
            for issue in issues
            if isinstance(issue, dict) and "pull_request" not in issue
        ],
        indent=2,
    )


def _exec_get_issue(tool_input: dict[str, Any], client: GitHubClient) -> str:
    """Fetch one issue with its recent discussion."""
    repo = str(tool_input["repo"])
    number = int(tool_input["number"])
    issue = client.get_issue(repo, number)
    comments = client.list_issue_comments(repo, number)
    result = _issue_summary(issue)
    result["body"] = _truncate(str(issue.get("body") or ""), _MAX_BODY_CHARS)
    result["comments"] = _comment_summaries(
        comments if isinstance(comments, list) else []
    )
    return json.dumps(result, indent=2)


def _exec_get_ci_status(tool_input: dict[str, Any], client: GitHubClient) -> str:
    """Summarize check runs for a ref (default branch when omitted)."""
    repo = str(tool_input["repo"])
    ref = str(tool_input.get("ref") or "")
    if not ref:
        ref = str(client.get_repo(repo).get("default_branch") or "main")
    raw = client.get_check_runs(repo, ref)
    runs = raw.get("check_runs", []) if isinstance(raw, dict) else []
    conclusions: dict[str, int] = {}
    summaries = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        conclusion = str(run.get("conclusion") or run.get("status") or "unknown")
        conclusions[conclusion] = conclusions.get(conclusion, 0) + 1
        summaries.append(
            {
                "name": run.get("name"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "url": run.get("html_url", ""),
            }
        )
    return json.dumps(
        {"ref": ref, "summary": conclusions, "checks": summaries}, indent=2
    )


_HANDLERS: dict[str, Callable[[dict[str, Any], GitHubClient], str]] = {
    "list_repos": _exec_list_repos,
    "get_repo": _exec_get_repo,
    "search_code": _exec_search_code,
    "get_file": _exec_get_file,
    "list_pull_requests": _exec_list_pull_requests,
    "get_pull_request": _exec_get_pull_request,
    "list_issues": _exec_list_issues,
    "get_issue": _exec_get_issue,
    "get_ci_status": _exec_get_ci_status,
}


def execute_tool(
    name: str,
    tool_input: dict[str, Any],
    client: GitHubClient,
) -> str:
    """Execute a tool call against the GitHub API and return a JSON string result.

    Parameters
    ----------
    name : str
        Tool name (any name in :data:`GITHUB_TOOL_NAMES`).
    tool_input : dict
        Tool input as provided by the model.
    client : GitHubClient
        Authenticated, org-pinned GitHub API client.

    Returns
    -------
    str
        JSON-encoded result, or an error message string.

    """
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Unknown tool: {name}"
    try:
        return handler(tool_input, client)
    except Exception as e:  # noqa: BLE001
        return f"Error executing {name}: {e}"
