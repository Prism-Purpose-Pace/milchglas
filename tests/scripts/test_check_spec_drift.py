"""check_spec_drift.py: one fact in one place - config keys and placeholder thresholds.

Catalogue GATE-13.

Fixtures are the real docs/spec.md and CLAUDE.md of this checkout, mutated in place, plus
the config.json row of docs/architecture.md copied verbatim from branch
docs/c4-architecture (spec v0.3 era, the row that still names `token`).
"""

from pathlib import Path

import pytest

import check_spec_drift as csd

REPO = Path(__file__).resolve().parents[2]
SPEC = (REPO / "docs" / "spec.md").read_text(encoding="utf-8")
GUIDE = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
STALE_ROW = (
    "| config.json | Container database (JSON file) | Non-secret configuration: `tz`,"
    " `window_days` (28), `grid_minutes` (15), `summary`, `ttl_seconds` (900), `allday_mode`,"
    " `tentative_mode`, `owner_emails`, `calendars[] {href, name, enabled}`, `token`. Lives on"
    " the volume or as a mounted file. Edits apply on the next refresh. | section 8 (config);"
    " FR-12; AC-10 |\n"
)


def swap(text: str, old: str, new: str) -> str:
    assert old in text, f"fixture drifted: {old!r} not found"
    return text.replace(old, new)


CLEAN_ROW = swap(STALE_ROW, "`token`.", "`token_sha256`, `uid_salt`.")


def tree(
    root: Path,
    *,
    spec: str | None = SPEC,
    guide: str | None = GUIDE,
    architecture: str | None = None,
    threat_model: str | None = None,
) -> Path:
    files = {
        "docs/spec.md": spec,
        "CLAUDE.md": guide,
        "docs/architecture.md": architecture,
        "docs/threat-model.md": threat_model,
    }
    for name, text in files.items():
        if text is not None:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    return root


def check(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = csd.main(["--root", str(root)])
    return code, capsys.readouterr().err


def test_clean_tree_exits_0_without_a_notice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tree(tmp_path, architecture=CLEAN_ROW, threat_model="`tz` and `window_days`.\n")
    assert check(root, capsys) == (0, "")


def test_the_repository_tree_is_clean(capsys: pytest.CaptureFixture[str]) -> None:
    assert check(REPO, capsys)[0] == 0


def test_absent_c4_documents_are_skipped_not_failed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, err = check(tree(tmp_path), capsys)
    assert code == 0
    assert "skipped: docs/architecture.md not in tree" in err
    assert "skipped: docs/threat-model.md not in tree" in err


def test_default_root_is_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tree(tmp_path, architecture=STALE_ROW))
    assert csd.main([]) == 1


def test_guide_missing_a_key_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    guide = swap(GUIDE, "`token_sha256`, `uid_salt`", "`token_sha256`")
    code, err = check(tree(tmp_path, guide=guide), capsys)
    assert code == 1
    # The guide is the real file, so take the list's first line from it, not a literal.
    line = next(n for n, text in enumerate(guide.splitlines(), 1) if "one `config.json`" in text)
    assert f"CLAUDE.md:{line}: config key `uid_salt` is in the spec" in err
    assert err.count("config key") == 1


def test_guide_with_an_extra_key_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    guide = swap(GUIDE, "`uid_salt`)", "`uid_salt`, `token`)")
    code, err = check(tree(tmp_path, guide=guide), capsys)
    assert code == 1
    assert "config key `token` is not in the spec's key list" in err
    assert err.count("config key") == 1


def test_guide_without_the_key_list_reports_every_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, err = check(tree(tmp_path, guide="# Guide\n\nNo settings listed.\n"), capsys)
    assert code == 1
    assert err.count("is in the spec") == len(csd.config_keys(SPEC)[1])


def test_stale_architecture_row_names_the_key_and_the_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, err = check(tree(tmp_path, architecture="# C4\n\n" + STALE_ROW), capsys)
    assert code == 1
    assert "docs/architecture.md:3: config key `token` is not in the spec's key list" in err
    assert err.count("config key") == 1


def test_corrected_architecture_row_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert check(tree(tmp_path, architecture=CLEAN_ROW), capsys)[0] == 0


@pytest.mark.parametrize(
    "prose",
    [
        "A test loads a `config.json` with a plain `token` key and expects a failure.\n",
        "Rename the config key `token` before the release.\n",
        "The `ttl` setting and the `window_days` value.\n",
    ],
)
def test_noun_next_to_an_unknown_key_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], prose: str
) -> None:
    code, err = check(tree(tmp_path, threat_model=prose), capsys)
    assert code == 1
    assert "docs/threat-model.md:1: config key" in err


@pytest.mark.parametrize(
    "prose",
    [
        "1. `refresher` reads `config.json` and its environment.\n",
        "`web` mounts `config.json` read-only; `web` has no write access.\n",
        "The `tz` key, the `href` field and the `enabled` setting are valid.\n",
        "Dropped: `summary`, `description` and `location`.\n",
        "Lists stop at a non-key span: `tz`, `window_days`, `config.json`, `web`.\n",
        "Lists stop at a blank line: `tz`, `window_days`,\n\n`web`.\n",
        "Lists stop at a pipe: `tz`, `window_days` | `web`.\n",
        "Environment, not config: `CALDAV_URL`, `tz`, `MILCHGLAS_VAR_DIR`.\n",
    ],
)
def test_names_that_are_not_config_keys_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], prose: str
) -> None:
    assert check(tree(tmp_path, threat_model=prose), capsys)[0] == 0


def test_key_list_wrapped_over_lines_is_still_a_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prose = "Keys: `tz`, `window_days`,\n`grid_minutes`, `token`.\n"
    code, err = check(tree(tmp_path, architecture=prose), capsys)
    assert code == 1
    assert "docs/architecture.md:2: config key `token`" in err


def test_a_list_joined_by_and_and_a_default_note_is_a_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prose = "Set `tz` (Europe/Berlin), `summary` and `retention` per host.\n"
    assert check(tree(tmp_path, architecture=prose), capsys)[0] == 1


def test_a_fenced_block_is_not_scanned(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fenced = f"```text\n{STALE_ROW}```\n"
    assert check(tree(tmp_path, architecture=fenced), capsys)[0] == 0
    assert check(tree(tmp_path, architecture=STALE_ROW), capsys)[0] == 1


def test_guide_list_ends_at_the_next_bullet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = "- Secrets and paths only via environment:"
    guide = swap(GUIDE, old, "- Also `unrelated` notes; secrets and paths via environment:")
    assert check(tree(tmp_path, guide=guide), capsys)[0] == 0


def test_guide_list_ends_at_a_blank_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    guide = swap(
        GUIDE, "never the token itself (spec D-14).\n", "never the token (D-14).\n\n`late`\n"
    )
    assert check(tree(tmp_path, guide=guide), capsys)[0] == 0


def test_config_keys_come_from_the_backticked_keys_only() -> None:
    spec = (
        "intro\n\n**Config (`config.json`, non-secret):** `tz`, `window_days` (33),"
        " `calendars[] {href, name, enabled}`, `token_sha256` (hex SHA-256 of the feed token;"
        " never stored).\nValidated on every refresh.\n\nAfter the blank line: `late_key`.\n"
    )
    line, top, nested = csd.config_keys(spec)
    assert (line, top, nested) == (
        3,
        {"tz", "window_days", "calendars", "token_sha256"},
        {
            "href",
            "name",
            "enabled",
        },
    )


def test_the_real_spec_lists_the_keys_the_guide_names() -> None:
    top = csd.config_keys(SPEC)[1]
    assert {"tz", "window_days", "token_sha256", "uid_salt"} <= top
    assert not {"token", "hex", "feed", "href"} & top


def test_spec_without_the_anchor_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = swap(SPEC, csd.ANCHOR, "**Settings:**")
    code, err = check(tree(tmp_path, spec=spec), capsys)
    assert code == 2
    assert "anchor" in err


def test_anchor_without_a_key_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, err = check(tree(tmp_path, spec=f"{csd.ANCHOR} none yet.\n"), capsys)
    assert code == 2
    assert "no backticked key" in err


@pytest.mark.parametrize("missing", ["spec", "guide"])
def test_a_missing_required_file_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], missing: str
) -> None:
    code, err = check(tree(tmp_path, **{missing: None}), capsys)
    assert code == 2
    assert "required file not found" in err


@pytest.mark.parametrize(
    "phrase",
    ["a stated bound", "a Stated Score", "the STATED THRESHOLD", "a stated value"],
)
def test_placeholder_threshold_in_the_spec_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], phrase: str
) -> None:
    spec = SPEC + f"\nThe check passes within {phrase}.\n"
    code, err = check(tree(tmp_path, spec=spec), capsys)
    assert code == 1
    assert f"docs/spec.md:{SPEC.count(chr(10)) + 2}: placeholder" in err


def test_stated_in_another_sense_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    spec = SPEC + "\nThe rule stated above; a bound is stated as a number of seconds.\n"
    assert check(tree(tmp_path, spec=spec), capsys)[0] == 0
