"""release-please must bump every place that carries the version, or the release PR fails.

`uv lock --check` (required check `lint`) goes red when pyproject.toml and uv.lock
disagree, so the lock entry is an extra file. release-please's TOML updater parses with
a tagging parser that wraps every scalar as {start, end, value}: the filter must compare
`@.name.value`; a plain `@.name` matches nothing and leaves uv.lock untouched.
"""

import json
import tomllib
from pathlib import Path

import milchglas

REPO = Path(__file__).resolve().parents[2]
LOCK_JSONPATH = "$.package[?(@.name.value=='milchglas')].version"


def test_uv_lock_extra_file_uses_the_tagged_toml_jsonpath() -> None:
    config = json.loads((REPO / "release-please-config.json").read_text(encoding="utf-8"))
    extra_files = config["packages"]["."]["extra-files"]
    assert {"type": "toml", "path": "uv.lock", "jsonpath": LOCK_JSONPATH} in extra_files


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
