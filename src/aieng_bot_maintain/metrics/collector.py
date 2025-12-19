"""Metrics collection for bot PR monitoring across VectorInstitute repositories."""

import json
import os
import subprocess
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any


class MetricsCollector:
    """Collects and aggregates metrics about bot PR activity.

    This class queries GitHub for bot PRs (Dependabot and pre-commit-ci),
    classifies their status, analyzes failure types, and generates comprehensive
    statistics for monitoring bot performance.

    Parameters
    ----------
    days_back : int, optional
        Number of days to look back for PRs (default=30).

    Attributes
    ----------
    days_back : int
        Number of days to query for PRs.

    """

    def __init__(self, days_back: int = 30):
        """Initialize the metrics collector.

        Parameters
        ----------
        days_back : int, optional
            Number of days to look back for PRs (default=30).

        """
        self.days_back = days_back

    def _run_gh_command(self, cmd: list[str]) -> str:
        """Execute a GitHub CLI command and return output.

        Parameters
        ----------
        cmd : list[str]
            Command and arguments to execute.

        Returns
        -------
        str
            Stripped stdout from command execution.

        Raises
        ------
        subprocess.CalledProcessError
            If the command fails.

        """
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def query_bot_prs(self) -> list[dict[str, Any]]:
        """Query GitHub for bot PRs in the last N days.

        Uses GitHub GraphQL API to search for PRs from Dependabot and
        pre-commit-ci across the VectorInstitute organization.

        Returns
        -------
        list[dict[str, Any]]
            List of PR objects with relevant fields including repository,
            number, title, author, timestamps, commits, and status checks.

        Notes
        -----
        Returns empty list if query fails (errors are printed).

        """
        since_date = (datetime.now(UTC) - timedelta(days=self.days_back)).strftime(
            "%Y-%m-%d"
        )

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
            result = self._run_gh_command(
                ["gh", "api", "graphql", "-f", f"query=@{query_file}"]
            )
            data = json.loads(result)
            return [edge["node"] for edge in data["search"]["edges"]]
        except subprocess.CalledProcessError as e:
            print(f"Error querying GitHub API: {e.stderr}")
            return []
        except json.JSONDecodeError as e:
            print(f"Error parsing GitHub API response: {e}")
            return []

    def classify_pr_status(self, pr: dict[str, Any]) -> str:
        """Classify PR status based on state and commits.

        Parameters
        ----------
        pr : dict[str, Any]
            PR object from GitHub API with state, mergedAt, and commits.

        Returns
        -------
        str
            One of: "auto_merged", "bot_fixed", "failed", "open".

        Notes
        -----
        - "auto_merged": PR was merged without bot intervention
        - "bot_fixed": PR was merged after bot made commits
        - "failed": PR was closed without merging
        - "open": PR is still open

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

    def analyze_failure_type(self, pr: dict[str, Any]) -> str | None:
        """Analyze failure type from status checks.

        Examines failed status checks and categorizes them into common
        failure types using keyword matching.

        Parameters
        ----------
        pr : dict[str, Any]
            PR object with statusCheckRollup field.

        Returns
        -------
        str or None
            One of: "test", "lint", "security", "build", "unknown", or None
            if no failures detected.

        Notes
        -----
        Returns None if no failed checks are found.
        Returns "unknown" if failed checks don't match known categories.

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

    def calculate_fix_time(self, pr: dict[str, Any]) -> float | None:
        """Calculate time to fix in hours.

        Parameters
        ----------
        pr : dict[str, Any]
            PR object with createdAt and mergedAt timestamps.

        Returns
        -------
        float or None
            Hours between PR creation and merge, or None if not merged.

        """
        if not pr.get("mergedAt"):
            return None

        created = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
        merged = datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))

        return (merged - created).total_seconds() / 3600

    def _update_status_counters(self, stats: dict[str, Any], status: str) -> None:
        """Update overall statistics counters based on PR status.

        Parameters
        ----------
        stats : dict[str, Any]
            Statistics dictionary to update.
        status : str
            PR status (auto_merged, bot_fixed, failed, open).

        """
        if status == "auto_merged":
            stats["prs_auto_merged"] += 1
        elif status == "bot_fixed":
            stats["prs_bot_fixed"] += 1
        elif status == "failed":
            stats["prs_failed"] += 1
        elif status == "open":
            stats["prs_open"] += 1

    def _update_failure_type_stats(
        self,
        by_failure_type: dict[str, dict[str, Any]],
        failure_type: str,
        status: str,
    ) -> None:
        """Update failure type statistics.

        Parameters
        ----------
        by_failure_type : dict[str, dict[str, Any]]
            Failure type statistics to update.
        failure_type : str
            Type of failure (test, lint, security, build, unknown).
        status : str
            PR status (auto_merged, bot_fixed, failed, open).

        """
        by_failure_type[failure_type]["count"] += 1
        if status in ["auto_merged", "bot_fixed"]:
            by_failure_type[failure_type]["fixed"] += 1
        elif status == "failed":
            by_failure_type[failure_type]["failed"] += 1

    def _update_repo_stats(
        self, by_repo: dict[str, dict[str, Any]], repo: str, status: str
    ) -> None:
        """Update repository statistics.

        Parameters
        ----------
        by_repo : dict[str, dict[str, Any]]
            Repository statistics to update.
        repo : str
            Repository name (owner/repo format).
        status : str
            PR status (auto_merged, bot_fixed, failed, open).

        """
        by_repo[repo]["total_prs"] += 1
        if status == "auto_merged":
            by_repo[repo]["auto_merged"] += 1
        elif status == "bot_fixed":
            by_repo[repo]["bot_fixed"] += 1
        elif status == "failed":
            by_repo[repo]["failed"] += 1

    def aggregate_metrics(self, prs: list[dict[str, Any]]) -> dict[str, Any]:
        """Calculate aggregate metrics from PRs.

        Processes a list of PRs and generates comprehensive statistics
        including overall stats, per-failure-type breakdowns, and
        per-repository breakdowns.

        Parameters
        ----------
        prs : list[dict[str, Any]]
            List of PR objects from query_bot_prs().

        Returns
        -------
        dict[str, Any]
            Dictionary with keys:
            - snapshot_date : str
                Date of metrics snapshot.
            - stats : dict
                Overall statistics (total, auto_merged, bot_fixed, failed,
                success_rate, avg_fix_time_hours).
            - by_failure_type : dict
                Statistics grouped by failure type.
            - by_repo : dict
                Statistics grouped by repository.

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

        by_failure_type: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "fixed": 0, "failed": 0, "success_rate": 0.0}
        )

        by_repo: dict[str, dict[str, Any]] = defaultdict(
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
            status = self.classify_pr_status(pr)
            repo = pr["repository"]["nameWithOwner"]
            failure_type = self.analyze_failure_type(pr) or "unknown"

            # Update statistics using helper methods
            self._update_status_counters(stats, status)
            self._update_failure_type_stats(by_failure_type, failure_type, status)
            self._update_repo_stats(by_repo, repo, status)

            # Calculate fix time
            fix_time = self.calculate_fix_time(pr)
            if fix_time is not None:
                fix_times.append(fix_time)

        # Calculate success rates
        total_completed = (
            stats["prs_auto_merged"] + stats["prs_bot_fixed"] + stats["prs_failed"]
        )
        if total_completed > 0:
            stats["success_rate"] = round(
                (stats["prs_auto_merged"] + stats["prs_bot_fixed"]) / total_completed,
                3,
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

    def load_history(self, filepath: str) -> dict[str, Any]:
        """Load existing history file if it exists.

        Parameters
        ----------
        filepath : str
            Path to history JSON file.

        Returns
        -------
        dict[str, Any]
            History data with snapshots and last_updated, or empty structure
            if file doesn't exist.

        """
        if os.path.exists(filepath):
            with open(filepath) as f:
                return json.load(f)
        return {"snapshots": [], "last_updated": None}

    def save_metrics(
        self,
        metrics: dict[str, Any],
        output_file: str,
        history_file: str | None = None,
    ) -> None:
        """Save metrics to JSON files.

        Parameters
        ----------
        metrics : dict[str, Any]
            Current metrics snapshot from aggregate_metrics().
        output_file : str
            Path to save latest metrics snapshot.
        history_file : str or None, optional
            Path to append metrics to historical data (default=None).

        Notes
        -----
        Creates parent directories if they don't exist.
        Prints status messages to stdout.

        """
        # Save latest snapshot
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(metrics, f, indent=2)

        print(f"✓ Latest metrics saved to {output_file}")

        # Append to history if specified
        if history_file:
            history = self.load_history(history_file)
            history["snapshots"].append(metrics)
            history["last_updated"] = datetime.now(UTC).isoformat()

            os.makedirs(os.path.dirname(history_file), exist_ok=True)
            with open(history_file, "w") as f:
                json.dump(history, f, indent=2)

            print(f"✓ History updated at {history_file}")

    def upload_to_gcs(self, local_file: str, bucket: str, destination: str) -> bool:
        """Upload file to Google Cloud Storage.

        Parameters
        ----------
        local_file : str
            Path to local file to upload.
        bucket : str
            GCS bucket name (without gs:// prefix).
        destination : str
            Destination path within bucket.

        Returns
        -------
        bool
            True if upload succeeded, False otherwise.

        Notes
        -----
        Uses gcloud CLI for upload (must be authenticated).
        Prints status messages to stdout.

        """
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
