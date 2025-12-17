#!/usr/bin/env python3
"""Script to automatically merge bot PRs with passing checks.

This script reads a list of GitHub repositories from a CSV file,
checks for open PRs from dependabot and pre-commit-ci, verifies all
checks have passed, and merges them automatically.

Usage:
    python merge_dependabot_prs.py repos.csv [--dry-run] [--merge-method {merge,squash,rebase}]
"""

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


class MergeMethod(str, Enum):
    """Supported PR merge methods."""

    MERGE = "merge"
    SQUASH = "squash"
    REBASE = "rebase"


class CheckStatus(str, Enum):
    """PR check status values."""

    SUCCESS = "success"
    PENDING = "pending"
    FAILURE = "failure"


@dataclass
class PullRequest:
    """Represents a GitHub Pull Request."""

    number: int
    title: str
    author: str
    url: str
    repo: str


class GitHubCLIError(Exception):
    """Raised when GitHub CLI commands fail."""

    pass


def run_gh_command(args: List[str], check: bool = True) -> str:
    """Execute a GitHub CLI command and return the output.

    Args:
        args: List of command arguments (without 'gh' prefix)
        check: Whether to raise an exception on non-zero exit code

    Returns:
        Command output as string

    Raises:
        GitHubCLIError: If command fails and check=True

    """
    cmd = ["gh"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_msg = f"GitHub CLI command failed: {' '.join(cmd)}\nError: {e.stderr}"
        raise GitHubCLIError(error_msg) from e
    except FileNotFoundError:
        raise GitHubCLIError(
            "GitHub CLI (gh) not found. Please install it from https://cli.github.com/"
        ) from None


def verify_gh_auth() -> bool:
    """Verify that GitHub CLI is authenticated.

    Returns:
        True if authenticated, False otherwise

    """
    try:
        run_gh_command(["auth", "status"])
        return True
    except GitHubCLIError:
        return False


def read_repos_from_csv(csv_path: Path) -> List[str]:
    """Read repository names from a CSV file.

    Expected CSV format:
    - First column contains repository names in format 'owner/repo'
    - Header row is optional and will be detected

    Args:
        csv_path: Path to the CSV file

    Returns:
        List of repository names

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV format is invalid

    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    repos = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)

        for i, row in enumerate(reader):
            if not row or not row[0].strip():
                continue

            repo = row[0].strip()

            # Skip potential header row
            if i == 0 and (
                "/" not in repo or repo.lower() in ["repo", "repository", "name"]
            ):
                continue

            # Validate repo format
            if "/" not in repo:
                console.print(
                    f"[yellow]Warning:[/yellow] Skipping invalid repo format: {repo}"
                )
                continue

            repos.append(repo)

    if not repos:
        raise ValueError(f"No valid repositories found in {csv_path}")

    return repos


def get_bot_prs(repo: str) -> List[PullRequest]:
    """Fetch all open bot PRs (dependabot and pre-commit-ci) for a repository.

    Args:
        repo: Repository name in format 'owner/repo'

    Returns:
        List of PullRequest objects

    """
    all_prs = []
    bot_authors = ["app/dependabot", "pre-commit-ci[bot]"]

    for author in bot_authors:
        try:
            # Query for open PRs from each bot
            output = run_gh_command(
                [
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--author",
                    author,
                    "--state",
                    "open",
                    "--json",
                    "number,title,author,url",
                ]
            )

            if not output:
                continue

            pr_data = json.loads(output)
            all_prs.extend(
                [
                    PullRequest(
                        number=pr["number"],
                        title=pr["title"],
                        author=pr["author"]["login"],
                        url=pr["url"],
                        repo=repo,
                    )
                    for pr in pr_data
                ]
            )
        except GitHubCLIError as e:
            console.print(f"[red]Error fetching {author} PRs for {repo}:[/red] {e}")
            continue

    return all_prs


def check_pr_status(pr: PullRequest) -> tuple[bool, str]:
    """Check if all CI checks have passed for a PR.

    Args:
        pr: PullRequest object

    Returns:
        Tuple of (all_passed: bool, status_message: str)

    """
    try:
        # Get PR checks status
        output = run_gh_command(
            [
                "pr",
                "checks",
                str(pr.number),
                "--repo",
                pr.repo,
                "--json",
                "state,name,completedAt",
            ]
        )

        if not output:
            return False, "No checks found"

        checks = json.loads(output)

        if not checks:
            # Some PRs might not have checks configured
            console.print(
                f"[yellow]Warning:[/yellow] PR #{pr.number} has no checks configured"
            )
            return False, "No checks configured"

        # Check if all checks have completed and passed
        pending_checks = []
        failed_checks = []

        for check in checks:
            state = check.get("state", "").lower()
            name = check.get("name", "Unknown")
            completed_at = check.get("completedAt")

            # Check is still running (not completed)
            if (
                state in ["pending", "queued", "in_progress", "waiting"]
                or not completed_at
            ):
                pending_checks.append(name)
            # Check completed but didn't succeed
            elif state not in ["success", "neutral", "skipped"]:
                # States like failure, error, cancelled, timed_out, action_required
                failed_checks.append(f"{name} ({state})")

        if failed_checks:
            return False, f"Failed checks: {', '.join(failed_checks)}"

        if pending_checks:
            return False, f"Pending checks: {', '.join(pending_checks)}"

        return True, "All checks passed"

    except GitHubCLIError as e:
        return False, f"Error checking status: {e}"


def merge_pr(pr: PullRequest, merge_method: MergeMethod, dry_run: bool = False) -> bool:
    """Merge a pull request.

    Args:
        pr: PullRequest object
        merge_method: Method to use for merging
        dry_run: If True, don't actually merge (just log what would happen)

    Returns:
        True if merge successful (or would be successful in dry-run), False otherwise

    """
    if dry_run:
        console.print(
            f"[yellow][DRY RUN][/yellow] Would merge PR #{pr.number} "
            f"using {merge_method.value} method"
        )
        return True

    # Try direct merge first
    try:
        run_gh_command(
            [
                "pr",
                "merge",
                str(pr.number),
                "--repo",
                pr.repo,
                f"--{merge_method.value}",
            ]
        )
        console.print(f"[green]✓[/green] Successfully merged PR #{pr.number}")
        return True
    except GitHubCLIError as e:
        error_msg = str(e)

        # If direct merge fails due to branch protection, try with --auto
        if "is not mergeable" in error_msg and "--auto" in error_msg:
            console.print(
                "  [dim]Branch protection requires auto-merge, retrying...[/dim]"
            )
            try:
                run_gh_command(
                    [
                        "pr",
                        "merge",
                        str(pr.number),
                        "--repo",
                        pr.repo,
                        f"--{merge_method.value}",
                        "--auto",
                    ]
                )
                console.print(
                    f"[green]✓[/green] Successfully enabled auto-merge for PR #{pr.number}"
                )
                return True
            except GitHubCLIError as auto_error:
                auto_error_msg = str(auto_error)
                # Check if it's the workflow scope issue
                if (
                    "workflow scope" in auto_error_msg
                    or "workflow`.yml`" in auto_error_msg
                ):
                    console.print(
                        f"[red]✗[/red] Cannot enable auto-merge for PR #{pr.number} (modifies workflow files)\n"
                        f"  [yellow]Action needed:[/yellow] GitHub CLI needs 'workflow' scope.\n"
                        f"  Run: [cyan]gh auth refresh -s workflow[/cyan]"
                    )
                else:
                    console.print(
                        f"[red]✗[/red] Failed to enable auto-merge for PR #{pr.number}: {auto_error}"
                    )
                return False
        else:
            console.print(f"[red]✗[/red] Failed to merge PR #{pr.number}: {e}")
            return False


def process_repository(repo: str, merge_method: MergeMethod, dry_run: bool) -> dict:
    """Process all bot PRs (dependabot and pre-commit-ci) in a repository.

    Args:
        repo: Repository name
        merge_method: Method to use for merging
        dry_run: If True, don't actually merge

    Returns:
        Dictionary with processing statistics

    """
    stats = {"total": 0, "merged": 0, "pending": 0, "failed": 0, "skipped": 0}

    console.print(f"\n[bold cyan]Processing repository:[/bold cyan] {repo}")

    # Fetch bot PRs
    prs = get_bot_prs(repo)
    stats["total"] = len(prs)

    if not prs:
        console.print("[dim]No open bot PRs found[/dim]")
        return stats

    console.print(f"Found {len(prs)} open bot PR(s)")

    # Process each PR
    for pr in prs:
        console.print(f"\n  PR #{pr.number}: [bold]{pr.title}[/bold]")
        console.print(f"  URL: {pr.url}")

        # Check PR status
        all_passed, status_msg = check_pr_status(pr)
        console.print(f"  Status: {status_msg}")

        if all_passed:
            # Attempt to merge
            if merge_pr(pr, merge_method, dry_run):
                stats["merged"] += 1
            else:
                stats["failed"] += 1
        elif "Pending" in status_msg:
            stats["pending"] += 1
            console.print("  [yellow]⏳[/yellow] Skipping - checks still running")
        else:
            stats["skipped"] += 1
            console.print("  [red]⏭[/red] Skipping - checks failed or incomplete")

    return stats


def create_summary_table(results: dict) -> Table:
    """Create a summary table of processing results.

    Args:
        results: Dictionary mapping repo names to their stats

    Returns:
        Rich Table object

    """
    table = Table(
        title="Processing Summary", show_header=True, header_style="bold magenta"
    )
    table.add_column("Repository", style="cyan")
    table.add_column("Total PRs", justify="right")
    table.add_column("Merged", justify="right", style="green")
    table.add_column("Pending", justify="right", style="yellow")
    table.add_column("Failed", justify="right", style="red")
    table.add_column("Skipped", justify="right", style="dim")

    total_stats = {"total": 0, "merged": 0, "pending": 0, "failed": 0, "skipped": 0}

    for repo, stats in results.items():
        table.add_row(
            repo,
            str(stats["total"]),
            str(stats["merged"]),
            str(stats["pending"]),
            str(stats["failed"]),
            str(stats["skipped"]),
        )
        for key in total_stats:
            total_stats[key] += stats[key]

    # Add totals row
    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_stats['total']}[/bold]",
        f"[bold]{total_stats['merged']}[/bold]",
        f"[bold]{total_stats['pending']}[/bold]",
        f"[bold]{total_stats['failed']}[/bold]",
        f"[bold]{total_stats['skipped']}[/bold]",
    )

    return table


def main():
    """Run the bot PR merging script."""
    parser = argparse.ArgumentParser(
        description="Automatically merge bot PRs (dependabot and pre-commit-ci) with passing checks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be merged
  python merge_dependabot_prs.py repos.csv --dry-run

  # Merge using squash method
  python merge_dependabot_prs.py repos.csv --merge-method squash

  # Merge with default settings (merge commit)
  python merge_dependabot_prs.py repos.csv
        """,
    )
    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to CSV file containing repository names (format: owner/repo)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be merged without actually merging",
    )
    parser.add_argument(
        "--merge-method",
        type=MergeMethod,
        choices=list(MergeMethod),
        default=MergeMethod.MERGE,
        help="Method to use for merging PRs (default: merge)",
    )

    args = parser.parse_args()

    # Print banner
    console.print(
        Panel.fit(
            "[bold blue]Bot PR Auto-Merger[/bold blue]\n"
            "Merges PRs from: dependabot, pre-commit-ci\n"
            f"Merge method: {args.merge_method.value}\n"
            f"Dry run: {'Yes' if args.dry_run else 'No'}",
            border_style="blue",
        )
    )

    try:
        # Verify GitHub CLI is authenticated
        console.print("\n[bold]Verifying GitHub CLI authentication...[/bold]")
        if not verify_gh_auth():
            console.print(
                "[red]Error:[/red] GitHub CLI is not authenticated. "
                "Please run 'gh auth login' first."
            )
            return 1
        console.print("[green]✓[/green] Authenticated")

        # Read repositories from CSV
        console.print(f"\n[bold]Reading repositories from {args.csv_file}...[/bold]")
        repos = read_repos_from_csv(args.csv_file)
        console.print(f"[green]✓[/green] Found {len(repos)} repository/repositories")

        # Process each repository
        results = {}
        for repo in repos:
            stats = process_repository(repo, args.merge_method, args.dry_run)
            results[repo] = stats

        # Display summary
        console.print("\n")
        console.print(create_summary_table(results))

        if args.dry_run:
            console.print(
                "\n[yellow]This was a dry run. No PRs were actually merged.[/yellow]"
            )

        return 0

    except (FileNotFoundError, ValueError, GitHubCLIError) as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        return 130
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
