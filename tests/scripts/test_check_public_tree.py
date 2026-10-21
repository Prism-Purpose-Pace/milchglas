"""check_public_tree.py: private paths and denylisted terms never reach the public tree."""

import os
import subprocess
from pathlib import Path

import pytest

import check_public_tree as cpt

PATTERNS = cpt.compile_patterns([r"acme\.example", r"\bsecretproject\b"])
REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path",
    [
        ".claude/settings.json",
        ".claude/hooks/check_bash.py",
        ".local/business.md",
        "docs/plans/spec.md",
        "docs/evidence/r1.md",
        "CLAUDE.local.md",
        ".worktrees/public/README.md",
    ],
)
def test_private_path_is_rejected(path: str) -> None:
    assert cpt.path_violations([path]) == [path]


@pytest.mark.parametrize(
    "path",
    [
        "CLAUDE.md",
        "docs/spec.md",
        "docs/planning.md",
        ".claude-template/settings.json",
        "src/milchglas/__init__.py",
        ".github/workflows/ci.yml",
    ],
)
def test_public_path_passes(path: str) -> None:
    assert cpt.path_violations([path]) == []


@pytest.mark.parametrize(
    "path",
    [
        "./.claude/settings.json",
        ".Claude/settings.json",
        "Docs/Plans/spec.md",
        "src/.claude/notes.md",
        "src/.local/notes.md",
        "docs/claude.local.md",
    ],
)
def test_private_path_variant_is_rejected(path: str) -> None:
    assert cpt.path_violations([path]) == [path]


def test_public_path_named_like_a_private_dir_passes() -> None:
    assert cpt.path_violations(["src/claude/x.py", "docs/local.md"]) == []


def test_latin1_file_is_scanned(tmp_path: Path) -> None:
    (tmp_path / "l.md").write_bytes(b"M\xfcller\nat acme.example\n")
    assert cpt.run(["l.md"], PATTERNS, tmp_path) == ["l.md:2: matches denylist pattern #1"]


def test_utf16_file_is_scanned(tmp_path: Path) -> None:
    (tmp_path / "u.md").write_text("at acme.example\n", encoding="utf-16")
    assert cpt.run(["u.md"], PATTERNS, tmp_path) == ["u.md:1: matches denylist pattern #1"]


def test_file_name_with_denylisted_term_is_reported(tmp_path: Path) -> None:
    (tmp_path / "acme.example-notes.md").write_text("clean\n", encoding="utf-8")
    assert cpt.run(["acme.example-notes.md"], PATTERNS, tmp_path) == [
        "acme.example-notes.md: file name matches denylist pattern #1"
    ]


@pytest.mark.parametrize(
    "text",
    ["acme\u200b.example\n", "acme\u2060.example\n", "\uff41\uff43\uff4d\uff45.example\n"],
    ids=["zero-width-space", "word-joiner", "fullwidth"],
)
def test_invisible_or_compatibility_characters_do_not_hide_a_term(text: str) -> None:
    assert cpt.term_violations("a.md", text, PATTERNS) == [cpt.Hit("a.md", 1, 0)]


def test_parse_log_scans_author_and_committer_identity() -> None:
    out = "abc1234\nJane <jane@acme.example>\nJane <jane@acme.example>\nfeat: x\n\x00"
    hits = cpt.message_violations(cpt.parse_log(out), PATTERNS)
    assert [cpt.format_hit(h) for h in hits] == [
        "commit abc1234:1: matches denylist pattern #1",
        "commit abc1234:2: matches denylist pattern #1",
    ]


def test_parse_log_with_clean_identity_passes() -> None:
    identity = "Jane <1+jane@users.noreply.github.com>"
    out = f"abc1234\n{identity}\n{identity}\nfeat: x\n\x00\ndef5678\n{identity}\n{identity}\nfix: y\n\x00"
    messages = cpt.parse_log(out)
    assert [sha for sha, _ in messages] == ["abc1234", "def5678"]
    assert cpt.message_violations(messages, PATTERNS) == []


def test_record_separator_in_a_commit_body_does_not_hide_a_term() -> None:
    identity = "Jane <1+jane@users.noreply.github.com>"
    body = f"chore: x\n\n{chr(0x1E)}at acme.example\n"
    out = f"abc1234\n{identity}\n{identity}\n{body}\x00"
    hits = cpt.message_violations(cpt.parse_log(out), PATTERNS)
    assert [cpt.format_hit(h) for h in hits] == ["commit abc1234:5: matches denylist pattern #1"]


@pytest.mark.parametrize(
    "separator",
    [chr(0x1C), chr(0x0B), chr(0x85), chr(0x2028), chr(0), "\r"],
    ids=["file-separator", "vertical-tab", "next-line", "line-separator", "nul", "carriage-return"],
)
def test_control_or_line_separator_inside_a_term_does_not_hide_it(separator: str) -> None:
    text = f"at acme{separator}.example\n"
    assert cpt.term_violations("a.md", text, PATTERNS) == [cpt.Hit("a.md", 1, 0)]


@pytest.mark.parametrize(
    "mark",
    [chr(0x301), chr(0xFE0F), chr(0x3164)],
    ids=["combining-acute", "variation-selector", "hangul-filler"],
)
def test_combining_mark_or_filler_inside_a_term_does_not_hide_it(mark: str) -> None:
    text = f"at acm{mark}e.example\n"
    assert cpt.term_violations("a.md", text, PATTERNS) == [cpt.Hit("a.md", 1, 0)]


def test_symlink_target_text_is_scanned(tmp_path: Path) -> None:
    (tmp_path / "link").symlink_to("/srv/acme.example/notes.md")
    assert cpt.run(["link"], PATTERNS, tmp_path) == ["link:1: matches denylist pattern #1"]


def test_symlink_target_content_is_not_followed(tmp_path: Path) -> None:
    (tmp_path / "target.md").write_text("at acme.example\n", encoding="utf-8")
    (tmp_path / "link").symlink_to("target.md")
    assert cpt.run(["link"], PATTERNS, tmp_path) == []


def test_denylisted_term_is_reported_with_line_and_pattern_index() -> None:
    hits = cpt.term_violations("README.md", "ok\nhosted at Acme.Example now\n", PATTERNS)
    assert hits == [cpt.Hit("README.md", 2, 0)]


def test_near_miss_text_has_no_term_hits() -> None:
    assert cpt.term_violations("README.md", "acme example, secretprojects\n", PATTERNS) == []


def test_report_never_echoes_the_matched_text_or_pattern() -> None:
    line = cpt.format_hit(cpt.Hit("README.md", 2, 0))
    assert line == "README.md:2: matches denylist pattern #1"
    assert "acme" not in line.lower()


def test_commit_message_hits_name_the_commit() -> None:
    hits = cpt.message_violations([("abc1234", "feat: x\n\nfor Acme.Example\n")], PATTERNS)
    assert [cpt.format_hit(h) for h in hits] == ["commit abc1234:3: matches denylist pattern #1"]


def test_clean_commit_message_passes() -> None:
    assert cpt.message_violations([("abc1234", "feat: add feed\n")], PATTERNS) == []


def test_parse_denylist_ignores_comments_and_blank_lines() -> None:
    patterns = cpt.parse_denylist("# comment\n\nacme\\.example\n   \n")
    assert [p.pattern for p in patterns] == [r"acme\.example"]


def test_patterns_match_case_insensitively() -> None:
    assert cpt.compile_patterns(["abc"])[0].search("xABCx") is not None


def test_invalid_pattern_fails_closed() -> None:
    with pytest.raises(cpt.DenylistError):
        cpt.compile_patterns(["("])


def test_non_ascii_pattern_is_rejected() -> None:
    # Text is NFKD-folded before matching, so a non-ASCII pattern could never match.
    with pytest.raises(cpt.DenylistError):
        cpt.compile_patterns(["m" + chr(0xFC) + "ller"])


def test_byte_order_mark_does_not_disable_the_first_pattern() -> None:
    patterns = cpt.parse_denylist(chr(0xFEFF) + "acme\\.example\n")
    assert [p.pattern for p in patterns] == [r"acme\.example"]


@pytest.mark.parametrize("code_point", [0xE000, 0xE0080], ids=["private-use", "unassigned"])
def test_private_use_or_unassigned_code_point_does_not_hide_a_term(code_point: int) -> None:
    text = f"at acme{chr(code_point)}.example\n"
    assert cpt.term_violations("a.md", text, PATTERNS) == [cpt.Hit("a.md", 1, 0)]


def test_unreadable_file_is_reported_not_crashed(tmp_path: Path) -> None:
    locked = tmp_path / "locked.md"
    locked.write_text("fine\n", encoding="utf-8")
    locked.chmod(0)
    try:
        assert cpt.run(["locked.md"], PATTERNS, tmp_path) == [
            "locked.md: unreadable, cannot be checked"
        ]
    finally:
        locked.chmod(0o600)


def test_ci_scans_only_the_commits_a_change_adds() -> None:
    # Commits GitHub creates itself (the merge preview, and the squash commit of a merged
    # PR) carry the account's bare display name, not the identity the branch commits carry.
    # Scanning the whole history therefore turned main red for good once one such commit
    # landed (a995e8f), and with it every later pull request. CI scans the range a change
    # adds instead: base..head on a pull request, before..sha on a push.
    ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "--commit-messages HEAD" not in ci
    assert '--commit-messages "$SCAN_REF"' not in ci
    assert '--commit-messages "$SCAN_RANGE"' in ci
    assert "github.event.pull_request.base.sha" in ci
    assert "github.event.before" in ci


def test_local_push_hook_scans_only_unpushed_commits() -> None:
    # Same defect as in CI, one level down: the pre-push hook scanned all of HEAD's
    # history, so the published a995e8f blocked every local push before CI ever ran.
    config = (REPO / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    entries = [line for line in config.splitlines() if "--commit-messages" in line]
    assert entries
    assert all(line.rstrip().endswith("--commit-messages origin/main..HEAD") for line in entries)


def test_commit_message_hook_runs_the_term_guard_on_the_message() -> None:
    # A private ID in a commit message was caught only at push, when it already needed a
    # reword of published-to-be history; the commit-msg stage catches it before it exists.
    config = (REPO / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    block = config.split("- id: check-public-tree-message", 1)[-1].split("- id:", 1)[0]
    assert "entry: uv run --script scripts/check_public_tree.py\n" in block
    assert "stages: [commit-msg]" in block


def test_commit_message_file_with_a_denylisted_term_is_reported(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/COMMIT_EDITMSG").write_text("fix: cite secretproject\n", encoding="utf-8")
    assert cpt.run([".git/COMMIT_EDITMSG"], PATTERNS, tmp_path)


def test_clean_commit_message_file_passes(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/COMMIT_EDITMSG").write_text("fix: cite Q-14\n", encoding="utf-8")
    assert cpt.run([".git/COMMIT_EDITMSG"], PATTERNS, tmp_path) == []


def _git(repo: Path, *args: str) -> str:
    env = {
        "PATH": os.environ["PATH"],
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "Dev",
        "GIT_AUTHOR_EMAIL": "dev@example.org",
        "GIT_COMMITTER_NAME": "Dev",
        "GIT_COMMITTER_EMAIL": "dev@example.org",
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


def test_a_range_leaves_published_history_below_its_base_unscanned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "published: acme.example")
    base = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "clean change")
    head = _git(tmp_path, "rev-parse", "HEAD")
    monkeypatch.chdir(tmp_path)
    assert cpt.message_violations(cpt.commit_messages(f"{base}..{head}"), PATTERNS) == []
    # the guard still guards: the same commit inside the scanned range is reported
    assert cpt.message_violations(cpt.commit_messages(head), PATTERNS)


def test_denylist_from_env_takes_precedence_over_file(tmp_path: Path) -> None:
    denylist = tmp_path / "deny.txt"
    denylist.write_text("fromfile\n", encoding="utf-8")
    patterns = cpt.load_denylist(denylist, {"PUBLIC_DENYLIST": "fromenv"})
    assert patterns is not None
    assert [p.pattern for p in patterns] == ["fromenv"]


def test_denylist_falls_back_to_file(tmp_path: Path) -> None:
    denylist = tmp_path / "deny.txt"
    denylist.write_text("fromfile\n", encoding="utf-8")
    patterns = cpt.load_denylist(denylist, {})
    assert patterns is not None
    assert [p.pattern for p in patterns] == ["fromfile"]


def test_linked_worktree_reads_the_main_checkout_denylist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The denylist is git-ignored, so a linked worktree has no copy of it: the default
    # path missed there and the term scan was skipped behind a passing hook.
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q")
    _git(main, "commit", "-q", "--allow-empty", "-m", "root")
    (main / cpt.DEFAULT_DENYLIST).parent.mkdir(parents=True)
    (main / cpt.DEFAULT_DENYLIST).write_text("secretproject\n", encoding="utf-8")
    _git(main, "worktree", "add", "-q", "--detach", str(tmp_path / "wt"))
    (tmp_path / "wt/note.md").write_text("about secretproject\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path / "wt")
    monkeypatch.delenv("PUBLIC_DENYLIST", raising=False)
    assert cpt.main(["note.md"]) == 1
    assert "note.md:1: matches denylist pattern #1" in capsys.readouterr().err


def test_repository_without_any_denylist_still_skips_the_term_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "note.md").write_text("about secretproject\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PUBLIC_DENYLIST", raising=False)
    assert cpt.main(["note.md"]) == 0
    assert "term scan skipped" in capsys.readouterr().err


def test_missing_denylist_yields_none(tmp_path: Path) -> None:
    assert cpt.load_denylist(tmp_path / "absent.txt", {}) is None


# A list that parses to zero patterns must read as "no denylist", not as "nothing is
# denied": an empty pattern list would pass --require-denylist and silently skip the
# whole term scan.
def test_denylist_file_without_patterns_yields_none(tmp_path: Path) -> None:
    denylist = tmp_path / "deny.txt"
    denylist.write_text("# only a comment\n\n   \n", encoding="utf-8")
    assert cpt.load_denylist(denylist, {}) is None


def test_denylist_env_without_patterns_yields_none(tmp_path: Path) -> None:
    denylist = tmp_path / "deny.txt"
    denylist.write_text("fromfile\n", encoding="utf-8")
    # The env var wins, so its emptiness must not fall back to the file either.
    assert cpt.load_denylist(denylist, {"PUBLIC_DENYLIST": "# only a comment\n"}) is None


def test_run_combines_path_and_term_findings(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("Acme.example\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("fine\n", encoding="utf-8")
    report = cpt.run(["a.md", "b.md", ".claude/x"], PATTERNS, tmp_path)
    assert report == [
        ".claude/x: private path must not be tracked in the public repo",
        "a.md:1: matches denylist pattern #1",
    ]


def test_run_skips_binary_and_missing_files(tmp_path: Path) -> None:
    (tmp_path / "img.png").write_bytes(b"\x89PNG\x00\xff\xfe")
    assert cpt.run(["img.png", "gone.md"], PATTERNS, tmp_path) == []


def test_run_without_denylist_checks_paths_only(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("Acme.example\n", encoding="utf-8")
    assert cpt.run(["a.md"], None, tmp_path) == []


def test_main_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PUBLIC_DENYLIST", raising=False)
    (tmp_path / "deny.txt").write_text("acme\\.example\n", encoding="utf-8")
    (tmp_path / "ok.md").write_text("fine\n", encoding="utf-8")
    (tmp_path / "bad.md").write_text("acme.example\n", encoding="utf-8")
    assert cpt.main(["--denylist", "deny.txt", "ok.md"]) == 0
    assert cpt.main(["--denylist", "deny.txt", "bad.md"]) == 1
    assert cpt.main(["--denylist", "deny.txt", ".claude/settings.json"]) == 1


def test_main_requires_denylist_when_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PUBLIC_DENYLIST", raising=False)
    (tmp_path / "ok.md").write_text("fine\n", encoding="utf-8")
    assert cpt.main(["--require-denylist", "--denylist", "absent.txt", "ok.md"]) == 2
    assert cpt.main(["--denylist", "absent.txt", "ok.md"]) == 0
