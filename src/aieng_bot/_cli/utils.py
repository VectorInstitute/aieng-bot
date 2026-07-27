"""Shared utilities for CLI commands."""

from importlib.metadata import PackageNotFoundError, version


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
