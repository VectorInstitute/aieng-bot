"""Bot Metrics Collection Script.

Collects aggregate metrics about bot PR activity across VectorInstitute repos:
- Total PRs scanned, auto-merged, fixed by bot, failed
- Success rates by failure type (test, lint, security, build)
- Per-repo statistics
- Time-series historical data

Usage:
    python scripts/collect_bot_metrics.py --output /path/to/output.json
"""

import argparse
import json
import os
import subprocess
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional


def run_gh_command(cmd: List[str]) -> str:
    """Run GitHub CLI command and return output."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def query_bot_prs(days_back: int = 30) -> List[Dict[str, Any]]:
    """Query GitHub for bot PRs in the last N days.

    Returns list of PR objects with relevant fields.
    """
    since_date = (datetime.now(UTC) - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # Use GraphQL to search for bot PRs
    query = f"""
    {{
      search(
        query: "org:VectorInstitute is:pr author:app/dependabot author:pre-commit-ci created:>={since_date}"
        type: ISSUE
        first: 100
      ) {{
        edges {{
          node {{
            ... on PullRequest {{
              repository {{ nameWithOwner }}
              number
              title
              author {{ login }}
              createdAt
              mergedAt
              closedAt
              state
              commits(last: 5) {{
                nodes {{
                  commit {{
                    author {{ name email }}
                    message
                  }}
                }}
              }}
              statusCheckRollup {{
                contexts(first: 50) {{
                  nodes {{
                    ... on StatusContext {{
                      context
                      state
                    }}
                    ... on CheckRun {{
                      name
                      conclusion
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """

    # Save query to temp file
    query_file = "/tmp/github-query.graphql"
    with open(query_file, "w") as f:
        f.write(query)

    # Execute GraphQL query
    try:
        result = run_gh_command(["gh", "api", "graphql", "-f", f"query=@{query_file}"])
        data = json.loads(result)
        return [edge["node"] for edge in data["search"]["edges"]]
    except subprocess.CalledProcessError as e:
        print(f"Error querying GitHub API: {e.stderr}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing GitHub API response: {e}")
        return []


def classify_pr_status(pr: Dict[str, Any]) -> str:
    """Classify PR status.

    Returns one of: auto_merged, bot_fixed, failed, open
    """
    if pr["state"] == "OPEN":
        return "open"

    # Check if merged
    if pr["mergedAt"]:
        # Check if bot made commits (indicating it was fixed by bot)
        bot_commit_found = False
        for commit in pr.get("commits", {}).get("nodes", []):
            commit_data = commit.get("commit", {})
            author_email = commit_data.get("author", {}).get("email", "")
            author_name = commit_data.get("author", {}).get("name", "")

            if "aieng-bot" in author_email or "aieng-bot" in author_name:
                bot_commit_found = True
                break

        if bot_commit_found:
            return "bot_fixed"
        return "auto_merged"

    # Closed without merging
    return "failed"


def analyze_failure_type(pr: Dict[str, Any]) -> Optional[str]:
    """Analyze what type of failure occurred based on status checks.

    Returns one of: test, lint, security, build, or None
    """
    status_rollup = pr.get("statusCheckRollup", {})
    contexts = (
        status_rollup.get("contexts", {}).get("nodes", []) if status_rollup else []
    )

    failed_checks = []
    for context in contexts:
        # Handle both StatusContext and CheckRun
        check_name = context.get("context") or context.get("name", "")
        conclusion = context.get("conclusion") or context.get("state", "")

        if conclusion in ["FAILURE", "failure"]:
            failed_checks.append(check_name.lower())

    if not failed_checks:
        return None

    # Categorize based on check names using a mapping
    check_str = " ".join(failed_checks)

    # Define categories with their keywords
    categories = {
        "test": ["test", "spec", "jest", "pytest", "unittest"],
        "lint": [
            "lint",
            "format",
            "pre-commit",
            "eslint",
            "prettier",
            "black",
            "flake8",
            "ruff",
        ],
        "security": ["audit", "security", "snyk", "dependabot", "pip-audit"],
        "build": ["build", "compile", "webpack", "vite", "tsc"],
    }

    # Find matching category
    for category, keywords in categories.items():
        if any(keyword in check_str for keyword in keywords):
            return category

    return "unknown"


def calculate_fix_time(pr: Dict[str, Any]) -> Optional[float]:
    """Calculate time to fix in hours.

    Returns hours between PR creation and merge, or None if not merged.
    """
    if not pr.get("mergedAt"):
        return None

    created = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
    merged = datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))

    return (merged - created).total_seconds() / 3600


def _update_status_counters(stats: Dict[str, Any], status: str) -> None:
    """Update overall statistics counters based on PR status."""
    if status == "auto_merged":
        stats["prs_auto_merged"] += 1
    elif status == "bot_fixed":
        stats["prs_bot_fixed"] += 1
    elif status == "failed":
        stats["prs_failed"] += 1
    elif status == "open":
        stats["prs_open"] += 1


def _update_failure_type_stats(
    by_failure_type: Dict[str, Dict[str, Any]], failure_type: str, status: str
) -> None:
    """Update failure type statistics."""
    by_failure_type[failure_type]["count"] += 1
    if status in ["auto_merged", "bot_fixed"]:
        by_failure_type[failure_type]["fixed"] += 1
    elif status == "failed":
        by_failure_type[failure_type]["failed"] += 1


def _update_repo_stats(
    by_repo: Dict[str, Dict[str, Any]], repo: str, status: str
) -> None:
    """Update repository statistics."""
    by_repo[repo]["total_prs"] += 1
    if status == "auto_merged":
        by_repo[repo]["auto_merged"] += 1
    elif status == "bot_fixed":
        by_repo[repo]["bot_fixed"] += 1
    elif status == "failed":
        by_repo[repo]["failed"] += 1


def aggregate_metrics(prs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate aggregate metrics from PRs.

    Returns dict with stats, by_failure_type, and by_repo breakdowns.
    """
    stats = {
        "total_prs_scanned": len(prs),
        "prs_auto_merged": 0,
        "prs_bot_fixed": 0,
        "prs_failed": 0,
        "prs_open": 0,
        "success_rate": 0.0,
        "avg_fix_time_hours": 0.0,
    }

    by_failure_type: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "fixed": 0, "failed": 0, "success_rate": 0.0}
    )

    by_repo: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "total_prs": 0,
            "auto_merged": 0,
            "bot_fixed": 0,
            "failed": 0,
            "success_rate": 0.0,
        }
    )

    fix_times = []

    for pr in prs:
        status = classify_pr_status(pr)
        repo = pr["repository"]["nameWithOwner"]
        failure_type = analyze_failure_type(pr) or "unknown"

        # Update statistics using helper functions
        _update_status_counters(stats, status)
        _update_failure_type_stats(by_failure_type, failure_type, status)
        _update_repo_stats(by_repo, repo, status)

        # Calculate fix time
        fix_time = calculate_fix_time(pr)
        if fix_time is not None:
            fix_times.append(fix_time)

    # Calculate success rates
    total_completed = (
        stats["prs_auto_merged"] + stats["prs_bot_fixed"] + stats["prs_failed"]
    )
    if total_completed > 0:
        stats["success_rate"] = round(
            (stats["prs_auto_merged"] + stats["prs_bot_fixed"]) / total_completed, 3
        )

    if fix_times:
        stats["avg_fix_time_hours"] = round(sum(fix_times) / len(fix_times), 2)

    # Calculate per-failure-type success rates
    for _ftype, data in by_failure_type.items():
        total = data["fixed"] + data["failed"]
        if total > 0:
            data["success_rate"] = round(data["fixed"] / total, 3)

    # Calculate per-repo success rates
    for _repo, data in by_repo.items():
        total = data["auto_merged"] + data["bot_fixed"] + data["failed"]
        if total > 0:
            data["success_rate"] = round(
                (data["auto_merged"] + data["bot_fixed"]) / total, 3
            )

    return {
        "snapshot_date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "stats": stats,
        "by_failure_type": dict(by_failure_type),
        "by_repo": dict(by_repo),
    }


def load_history(filepath: str) -> Dict[str, Any]:
    """Load existing history file if it exists."""
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {"snapshots": [], "last_updated": None}


def save_metrics(
    metrics: Dict[str, Any], output_file: str, history_file: Optional[str] = None
):
    """Save metrics to JSON files.

    Args:
        metrics: Current metrics snapshot
        output_file: Path to save latest metrics
        history_file: Optional path to append to history

    """
    # Save latest snapshot
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"✓ Latest metrics saved to {output_file}")

    # Append to history if specified
    if history_file:
        history = load_history(history_file)
        history["snapshots"].append(metrics)
        history["last_updated"] = datetime.now(UTC).isoformat()

        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)

        print(f"✓ History updated at {history_file}")


def upload_to_gcs(local_file: str, bucket: str, destination: str) -> bool:
    """Upload file to GCS."""
    try:
        subprocess.run(
            [
                "gcloud",
                "storage",
                "cp",
                local_file,
                f"gs://{bucket}/{destination}",
                "--content-type=application/json",
            ],
            check=True,
            capture_output=True,
        )
        print(f"✓ Uploaded to gs://{bucket}/{destination}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to upload to GCS: {e.stderr.decode()}")
        return False


def main():
    """Collect and aggregate bot PR metrics from GitHub."""
    parser = argparse.ArgumentParser(description="Collect bot PR metrics")
    parser.add_argument(
        "--days", type=int, default=30, help="Number of days to look back"
    )
    parser.add_argument(
        "--output",
        default="/tmp/bot_metrics_latest.json",
        help="Output file for latest metrics",
    )
    parser.add_argument(
        "--history",
        default="/tmp/bot_metrics_history.json",
        help="Output file for historical data",
    )
    parser.add_argument(
        "--upload-to-gcs", action="store_true", help="Upload results to GCS"
    )
    parser.add_argument(
        "--gcs-bucket", default="bot-dashboard-vectorinstitute", help="GCS bucket name"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Bot Metrics Collection")
    print("=" * 60)
    print(f"Looking back: {args.days} days")
    print("")

    # Query PRs
    print("Querying GitHub for bot PRs...")
    prs = query_bot_prs(days_back=args.days)
    print(f"✓ Found {len(prs)} bot PRs")
    print("")

    # Calculate metrics
    print("Calculating aggregate metrics...")
    metrics = aggregate_metrics(prs)
    print("✓ Metrics calculated")
    print("")

    # Print summary
    print("Summary:")
    print(f"  Total PRs: {metrics['stats']['total_prs_scanned']}")
    print(f"  Auto-merged: {metrics['stats']['prs_auto_merged']}")
    print(f"  Bot-fixed: {metrics['stats']['prs_bot_fixed']}")
    print(f"  Failed: {metrics['stats']['prs_failed']}")
    print(f"  Success rate: {metrics['stats']['success_rate']:.1%}")
    print(f"  Avg fix time: {metrics['stats']['avg_fix_time_hours']:.1f} hours")
    print("")

    # Save locally
    save_metrics(metrics, args.output, args.history)
    print("")

    # Upload to GCS if requested
    if args.upload_to_gcs:
        print("Uploading to GCS...")
        upload_to_gcs(args.output, args.gcs_bucket, "data/bot_metrics_latest.json")
        upload_to_gcs(args.history, args.gcs_bucket, "data/bot_metrics_history.json")
        print("")

    print("✓ Metrics collection complete")


if __name__ == "__main__":
    main()
