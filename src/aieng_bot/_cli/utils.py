"""Shared utilities for CLI commands."""

import argparse
import json
from importlib.metadata import PackageNotFoundError, version

from ..classifier.models import CheckFailure, PRContext
from ..utils.logging import log_error, log_info


def get_version() -> str:
    """Get the installed version of the package.

    Returns
    -------
    str
        Version string from package metadata.

    """
    try:
        return version("aieng-bot")
    except PackageNotFoundError:
        return "unknown"


def read_failure_logs(args: argparse.Namespace) -> str:
    """Read failure logs from file or command-line argument.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command-line arguments.

    Returns
    -------
    str
        Failure logs content.

    """
    if args.failure_logs_file:
        log_info(f"Reading failure logs from file: {args.failure_logs_file}")
        try:
            with open(args.failure_logs_file, "r") as f:
                failure_logs = f.read()
            log_info(f"Read {len(failure_logs)} characters from file")
            return failure_logs
        except FileNotFoundError:
            log_error(f"Failure logs file not found: {args.failure_logs_file}")
            return ""
    elif args.failure_logs:
        return args.failure_logs
    else:
        log_error("Neither --failure-logs nor --failure-logs-file provided")
        return ""


def parse_pr_inputs(
    args: argparse.Namespace,
) -> tuple[PRContext, list[CheckFailure]]:
    """Parse PR context and failed checks from command-line arguments.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command-line arguments.

    Returns
    -------
    tuple[PRContext, list[CheckFailure]]
        Parsed PR context and list of failed checks.

    """
    pr_data = json.loads(args.pr_info)
    checks_data = json.loads(args.failed_checks)

    pr_context = PRContext(
        repo=pr_data["repo"],
        pr_number=int(pr_data["pr_number"]),
        pr_title=pr_data["pr_title"],
        pr_author=pr_data["pr_author"],
        base_ref=pr_data["base_ref"],
        head_ref=pr_data["head_ref"],
    )

    failed_checks = [
        CheckFailure(
            name=check["name"],
            conclusion=check["conclusion"],
            workflow_name=check.get("workflowName", ""),
            details_url=check.get("detailsUrl", ""),
            started_at=check.get("startedAt", ""),
            completed_at=check.get("completedAt", ""),
        )
        for check in checks_data
    ]

    return pr_context, failed_checks
