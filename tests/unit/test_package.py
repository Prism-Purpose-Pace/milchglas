"""Smoke test: the package is installed into the project env and self-describes."""

from importlib.metadata import version

import milchglas


def test_version_matches_installed_distribution_metadata() -> None:
    assert milchglas.__version__ == version("milchglas")
