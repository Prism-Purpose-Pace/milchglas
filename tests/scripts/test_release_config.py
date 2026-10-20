"""release-please must bump every place that carries the version, or the release PR fails.

`uv lock --check` (required check `lint`) goes red when pyproject.toml and uv.lock
disagree, so the lock entry is an extra file. release-please's TOML updater parses with
a tagging parser that wraps every scalar as {start, end, value}: the filter must compare
`@.name.value`; a plain `@.name` matches nothing and leaves uv.lock untouched.
"""

import json
import re
import tomllib
from pathlib import Path

import milchglas

REPO = Path(__file__).resolve().parents[2]
LOCK_JSONPATH = "$.package[?(@.name.value=='milchglas')].version"


def test_uv_lock_extra_file_uses_the_tagged_toml_jsonpath() -> None:
    config = json.loads((REPO / "release-please-config.json").read_text(encoding="utf-8"))
    extra_files = config["packages"]["."]["extra-files"]
    assert {"type": "toml", "path": "uv.lock", "jsonpath": LOCK_JSONPATH} in extra_files


def test_last_release_sha_anchors_the_first_run() -> None:
    # The seed history is already inside 0.1.0. Without an anchor release-please would
    # walk back to the root and re-release every commit; a truncated or placeholder sha
    # is silently ignored, so the full 40 hex digits are the assertion.
    config = json.loads((REPO / "release-please-config.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{40}", config["last-release-sha"])


def test_versions_agree_across_manifest_pyproject_lock_and_package() -> None:
    manifest = json.loads((REPO / ".release-please-manifest.json").read_text(encoding="utf-8"))
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((REPO / "uv.lock").read_text(encoding="utf-8"))
    entries = [p for p in lock["package"] if p["name"] == "milchglas"]
    assert len(entries) == 1
    versions = {
        manifest["."],
        pyproject["project"]["version"],
        entries[0]["version"],
        milchglas.__version__,
    }
    assert len(versions) == 1


def test_changelog_has_a_header_for_the_current_version() -> None:
    # Without any version header release-please demotes the whole seed below the first
    # new entry; with one it inserts new entries above it and keeps the intro on top.
    manifest = json.loads((REPO / ".release-please-manifest.json").read_text(encoding="utf-8"))
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    header = rf"^## \[?{re.escape(manifest['.'])}\]?"
    assert re.search(header, changelog, re.MULTILINE)
