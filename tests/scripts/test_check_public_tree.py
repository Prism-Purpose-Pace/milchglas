"""check_public_tree.py: private paths and denylisted terms never reach the public tree."""

import errno
import io
import os
import shutil
import subprocess
import sys
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


def test_unreadable_file_is_reported_not_crashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # chmod(0) does not keep root out, so the read itself fails: the same except branch
    # runs whoever runs the suite.
    locked = tmp_path / "locked.md"
    locked.write_text("fine\n", encoding="utf-8")
    read_bytes = Path.read_bytes

    def deny(self: Path) -> bytes:
        if self == locked:
            raise PermissionError(errno.EACCES, "denied")
        return read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", deny)
    assert cpt.run(["locked.md"], PATTERNS, tmp_path) == [
        "locked.md: unreadable, cannot be checked"
    ]


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


def test_local_push_hook_scans_the_pushed_ref() -> None:
    # pre-commit hands a pre-push hook the pushed ref in its environment. A fixed
    # `<base>..HEAD` range scanned the checked-out branch instead, so `git push origin X`
    # with another branch checked out published X unscanned.
    config = (REPO / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    block = config.split("- id: check-public-tree-history", 1)[-1].split("- id:", 1)[0]
    assert "entry: uv run --script scripts/check_public_tree.py --pre-push\n" in block
    assert "stages: [pre-push]" in block
    assert "always_run: true" in block
    assert "pass_filenames: false" in block


def test_commit_message_hook_runs_the_term_guard_on_the_message() -> None:
    # A private ID in a commit message was caught only at push, when it already needed a
    # reword of published-to-be history; the commit-msg stage catches it before it exists.
    config = (REPO / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    block = config.split("- id: check-public-tree-message", 1)[-1].split("- id:", 1)[0]
    # --message-files: git hands a linked worktree's message over as an absolute path inside
    # the main checkout's .git; its directory names are not content to guard.
    assert "entry: uv run --script scripts/check_public_tree.py --message-files\n" in block
    assert "stages: [commit-msg]" in block


@pytest.mark.parametrize(
    "hook", ["check-public-tree", "check-public-tree-message", "check-public-tree-history"]
)
def test_guard_hooks_show_their_output_on_a_pass(hook: str) -> None:
    # pre-commit hides the output of a passing hook, so the skip notice ("no denylist found,
    # term scan skipped") stayed invisible behind `Passed`; verbose hooks print it.
    config = (REPO / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert f"- id: {hook}\n" in config
    block = config.split(f"- id: {hook}\n", 1)[-1].split("- id:", 1)[0]
    assert "verbose: true\n" in block


def test_commit_message_file_with_a_denylisted_term_is_reported(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/COMMIT_EDITMSG").write_text("fix: cite secretproject\n", encoding="utf-8")
    assert cpt.run([".git/COMMIT_EDITMSG"], PATTERNS, tmp_path)


def test_clean_commit_message_file_passes(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/COMMIT_EDITMSG").write_text("fix: cite Q-14\n", encoding="utf-8")
    assert cpt.run([".git/COMMIT_EDITMSG"], PATTERNS, tmp_path) == []


# In a linked worktree git hands the hook an absolute path inside the main checkout's
# .git (<main>/.git/worktrees/<n>/COMMIT_EDITMSG). Only the content of that file is the
# commit; a directory name above it is the maintainer's own, and must not refuse a clean
# message (the only way out would be --no-verify).
GUARDED_DIRECTORIES = pytest.mark.parametrize(
    "directory", ["acme.example", ".claude"], ids=["term-in-directory", "private-directory"]
)


def _message_file(tmp_path: Path, directory: str, text: str) -> Path:
    message = tmp_path / directory / ".git/worktrees/wt1/COMMIT_EDITMSG"
    message.parent.mkdir(parents=True)
    message.write_text(text, encoding="utf-8")
    return message


def _denylist_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.delenv("PUBLIC_DENYLIST", raising=False)
    (tmp_path / "deny.txt").write_text("\n".join(p.pattern for p in PATTERNS), encoding="utf-8")
    return str(tmp_path / "deny.txt")


@GUARDED_DIRECTORIES
def test_clean_message_file_under_a_guarded_directory_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, directory: str
) -> None:
    deny = _denylist_file(tmp_path, monkeypatch)
    message = _message_file(tmp_path, directory, "fix: cite Q-14\n")
    assert cpt.main(["--denylist", deny, "--message-files", str(message)]) == 0


@GUARDED_DIRECTORIES
def test_banned_message_file_under_a_guarded_directory_is_reported_by_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    directory: str,
) -> None:
    deny = _denylist_file(tmp_path, monkeypatch)
    message = _message_file(tmp_path, directory, "fix: x\n\ncite secretproject\n")
    assert cpt.main(["--denylist", deny, "--message-files", str(message)]) == 1
    err = capsys.readouterr().err
    # one finding: the content hit by line and pattern index, no path or name finding
    assert err.splitlines() == [
        f"{message}:3: matches denylist pattern #2",
        "check-public-tree: 1 finding(s)",
    ]
    assert "secretproject" not in err.lower()


def test_message_files_without_a_path_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Without a path the guard would fall back to every tracked file, path guard off.
    deny = _denylist_file(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as exit_info:
        cpt.main(["--denylist", deny, "--message-files"])
    assert exit_info.value.code == 2
    assert "needs at least one path" in capsys.readouterr().err


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


# --pre-push: pre-commit exports the pushed ref (PRE_COMMIT_TO_REF, or the local branch when
# the push has no new-commits range) and the guard scans THAT commit, not HEAD or the
# working tree. Every test runs in a tmp repo with HEAD = main = origin/main and a clean
# README; branch x is never checked out.
PUSH_ENV = (
    "PRE_COMMIT_FROM_REF",
    "PRE_COMMIT_TO_REF",
    "PRE_COMMIT_LOCAL_BRANCH",
    "PRE_COMMIT_REMOTE_BRANCH",
    "PRE_COMMIT_REMOTE_NAME",
    "PRE_COMMIT_REMOTE_URL",
)
TERM_MESSAGE = "feat: cite secretproject"
TERM_TEXT = b"about secretproject\n"


def _commit_files(repo: Path, files: dict[str, bytes], message: str) -> str:
    for name, data in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_bytes(data)
        _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _branch_x(repo: Path, files: dict[str, bytes], message: str) -> str:
    """Commit on branch x, one ahead of main, then back on main; return the commit."""
    _git(repo, "checkout", "-q", "-b", "x")
    sha = _commit_files(repo, files, message)
    _git(repo, "checkout", "-q", "main")
    return sha


@pytest.fixture
def push_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # the hooks run pytest inside a push: a leaked PRE_COMMIT_* would steer these tests
    for name in PUSH_ENV:
        monkeypatch.delenv(name, raising=False)
    _denylist_file(tmp_path, monkeypatch)  # outside the repo, so it is no working-tree file
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit_files(repo, {"README.md": b"clean\n"}, "chore: root")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    monkeypatch.chdir(repo)
    return repo


def _pre_push(repo: Path) -> int:
    return cpt.main(["--denylist", str(repo.parent / "deny.txt"), "--pre-push"])


def test_pre_push_scans_the_pushed_branch_not_head(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pushed = _branch_x(push_repo, {"notes.md": TERM_TEXT}, TERM_MESSAGE)
    monkeypatch.setenv("PRE_COMMIT_TO_REF", pushed)
    assert _pre_push(push_repo) == 1
    short = _git(push_repo, "rev-parse", "--short", pushed)
    err = capsys.readouterr().err
    # the file in the pushed commit, then its message (author and committer are lines 1-2)
    assert err.splitlines() == [
        f"{short}:notes.md:1: matches denylist pattern #2",
        f"commit {short}:3: matches denylist pattern #2",
        "check-public-tree: 2 finding(s)",
    ]
    assert "secretproject" not in err.lower()


def test_pre_push_passes_a_clean_pushed_branch(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pushed = _branch_x(push_repo, {"notes.md": b"fine\n"}, "feat: add notes")
    monkeypatch.setenv("PRE_COMMIT_TO_REF", pushed)
    assert _pre_push(push_repo) == 0


def test_pre_push_resolves_the_local_branch_when_pre_commit_sets_no_to_ref(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A push that includes a root commit gets no FROM/TO ref, only the branch names.
    _branch_x(push_repo, {"notes.md": TERM_TEXT}, TERM_MESSAGE)
    monkeypatch.setenv("PRE_COMMIT_REMOTE_NAME", "origin")
    monkeypatch.setenv("PRE_COMMIT_LOCAL_BRANCH", "refs/heads/x")
    assert _pre_push(push_repo) == 1


def test_pre_push_refuses_a_push_whose_ref_cannot_be_resolved(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Falling back to HEAD here would reopen the defect: it scans another ref than the pushed one.
    _branch_x(push_repo, {"notes.md": TERM_TEXT}, TERM_MESSAGE)
    monkeypatch.setenv("PRE_COMMIT_REMOTE_NAME", "origin")
    assert _pre_push(push_repo) == 1
    assert "cannot determine the pushed ref" in capsys.readouterr().err


def test_pre_push_without_a_push_environment_scans_head_not_other_branches(
    push_repo: Path,
) -> None:
    _branch_x(push_repo, {"notes.md": TERM_TEXT}, TERM_MESSAGE)
    assert _pre_push(push_repo) == 0


def test_pre_push_without_a_push_environment_reports_a_term_in_head(push_repo: Path) -> None:
    _commit_files(push_repo, {"head.md": TERM_TEXT}, TERM_MESSAGE)
    assert _pre_push(push_repo) == 1


@pytest.mark.parametrize(
    ("variable", "label"),
    [
        ("PRE_COMMIT_LOCAL_BRANCH", "ref local branch"),
        ("PRE_COMMIT_REMOTE_BRANCH", "ref remote branch"),
    ],
)
def test_pre_push_reports_a_denylisted_ref_name_without_echoing_it(
    push_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    variable: str,
    label: str,
) -> None:
    monkeypatch.setenv("PRE_COMMIT_TO_REF", _git(push_repo, "rev-parse", "HEAD"))
    monkeypatch.setenv(variable, "refs/heads/secretproject")
    assert _pre_push(push_repo) == 1
    err = capsys.readouterr().err
    assert err.splitlines() == [
        f"{label}: matches denylist pattern #2",
        "check-public-tree: 1 finding(s)",
    ]
    assert "secretproject" not in err.lower()


@pytest.mark.parametrize("variable", ["PRE_COMMIT_LOCAL_BRANCH", "PRE_COMMIT_REMOTE_BRANCH"])
def test_pre_push_passes_a_clean_ref_name(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv("PRE_COMMIT_TO_REF", _git(push_repo, "rev-parse", "HEAD"))
    monkeypatch.setenv(variable, "refs/heads/feature")
    assert _pre_push(push_repo) == 0


def test_pre_push_ignores_a_term_only_the_working_tree_holds(push_repo: Path) -> None:
    (push_repo / "scratch.md").write_bytes(TERM_TEXT)  # untracked
    (push_repo / "README.md").write_bytes(TERM_TEXT)  # tracked, modified, not committed
    assert _pre_push(push_repo) == 0
    # the guard does see such a file when it is named: the pass above is not blindness
    assert cpt.main(["--denylist", str(push_repo.parent / "deny.txt"), "README.md"]) == 1


@pytest.mark.parametrize("published", [True, False], ids=["published", "unpublished"])
def test_pre_push_scans_only_commits_not_yet_on_origin_main(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch, *, published: bool
) -> None:
    # Same defect class as the CI range: a published commit (a995e8f) must not block a push.
    _commit_files(push_repo, {"p.md": b"fine\n"}, TERM_MESSAGE)
    if published:
        _git(push_repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    pushed = _branch_x(push_repo, {"notes.md": b"fine\n"}, "feat: add notes")
    monkeypatch.setenv("PRE_COMMIT_TO_REF", pushed)
    assert _pre_push(push_repo) == (0 if published else 1)


@pytest.mark.parametrize(
    "case",  # (path, content, first finding)
    [
        (
            "docs/plans/p.md",
            b"fine\n",
            "docs/plans/p.md: private path must not be tracked in the public repo",
        ),
        (
            "secretproject-notes.md",
            b"fine\n",
            "secretproject-notes.md: file name matches denylist pattern #2",
        ),
        ("u.md", "about secretproject\n".encode("utf-16"), "u.md:1: matches denylist pattern #2"),
    ],
    ids=["private-path", "term-in-file-name", "utf-16-content"],
)
def test_pre_push_reports_what_the_pushed_tree_holds(
    push_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: tuple[str, bytes, str],
) -> None:
    path, data, finding = case
    pushed = _branch_x(push_repo, {path: data}, "feat: add file")
    monkeypatch.setenv("PRE_COMMIT_TO_REF", pushed)
    assert _pre_push(push_repo) == 1
    short = _git(push_repo, "rev-parse", "--short", pushed)
    assert capsys.readouterr().err.splitlines()[0] == f"{short}:{finding}"


@pytest.mark.parametrize(
    ("target", "expected"),
    [("/srv/secretproject/n", 1), ("docs/readme.md", 0)],
    ids=["term", "clean"],
)
def test_pre_push_scans_a_symlink_text_in_the_pushed_tree(
    push_repo: Path, target: str, expected: int
) -> None:
    (push_repo / "link").symlink_to(target)
    _git(push_repo, "add", "link")
    _git(push_repo, "commit", "-q", "-m", "feat: add link")
    assert _pre_push(push_repo) == expected


def test_pre_push_skips_a_gitlink_entry(push_repo: Path) -> None:
    # A gitlink names a commit of another repository; reading that object as a file would
    # scan its message. Here it points at a commit holding a term that is NOT in the pushed
    # history, so only a skipped gitlink passes.
    elsewhere = _branch_x(push_repo, {"n.md": b"fine\n"}, TERM_MESSAGE)
    _git(push_repo, "update-index", "--add", "--cacheinfo", f"160000,{elsewhere},sub")
    _git(push_repo, "commit", "-q", "-m", "chore: add pointer")
    assert _pre_push(push_repo) == 0


# --pre-push reads what a push transfers: every commit the remote lacks (`<pushed> --not
# --remotes=<remote>`, pre-commit's own rule for "new"), with its message, identities and every
# path and blob it adds or changes. The tip tree alone misses a term added and removed again
# inside the push; a literal `origin/main` base breaks for any other remote name.
PRIVATE_PATH_FINDING = "private path must not be tracked in the public repo"


def _remote(repo: Path, name: str) -> None:
    """A bare tmp remote `name` holding main as it is now (so refs/remotes/<name>/main exists)."""
    bare = repo.parent / f"{name}.git"
    _git(repo.parent, "init", "-q", "--bare", str(bare))
    _git(repo, "remote", "add", name, str(bare))
    _git(repo, "push", "-q", name, "main")


def _remove(repo: Path, name: str, message: str) -> str:
    _git(repo, "rm", "-q", name)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _push(monkeypatch: pytest.MonkeyPatch, remote: str, commit: str) -> None:
    monkeypatch.setenv("PRE_COMMIT_REMOTE_NAME", remote)
    monkeypatch.setenv("PRE_COMMIT_TO_REF", commit)


ON_REMOTE = pytest.mark.parametrize(
    "on_remote", [False, True], ids=["remote-lacks-A", "remote-has-A"]
)


@ON_REMOTE
def test_pre_push_reads_a_term_added_and_removed_inside_the_push(
    push_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    on_remote: bool,
) -> None:
    _remote(push_repo, "origin")
    added = _commit_files(push_repo, {"notes.md": TERM_TEXT}, "feat: add notes")  # commit A
    if on_remote:
        _git(push_repo, "push", "-q", "origin", "main")
    _push(monkeypatch, "origin", _remove(push_repo, "notes.md", "fix: drop notes"))  # commit B
    assert _pre_push(push_repo) == (0 if on_remote else 1)
    err = capsys.readouterr().err
    if on_remote:
        assert err == ""
    else:
        short = _git(push_repo, "rev-parse", "--short", added)
        assert err.splitlines() == [
            f"{short}:notes.md:1: matches denylist pattern #2",
            "check-public-tree: 1 finding(s)",
        ]
        assert "secretproject" not in err.lower()


@ON_REMOTE
def test_pre_push_reports_a_private_path_added_and_removed_inside_the_push(
    push_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    on_remote: bool,
) -> None:
    _remote(push_repo, "origin")
    added = _commit_files(push_repo, {".claude/x": b"fine\n"}, "feat: add x")
    if on_remote:
        _git(push_repo, "push", "-q", "origin", "main")
    _push(monkeypatch, "origin", _remove(push_repo, ".claude/x", "fix: drop x"))
    assert _pre_push(push_repo) == (0 if on_remote else 1)  # removing a published path is no leak
    short = _git(push_repo, "rev-parse", "--short", added)
    expected = [] if on_remote else [f"{short}:.claude/x: {PRIVATE_PATH_FINDING}"]
    assert capsys.readouterr().err.splitlines()[:1] == expected


@ON_REMOTE
def test_pre_push_leaves_a_message_the_remote_already_has_unscanned(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch, *, on_remote: bool
) -> None:
    _remote(push_repo, "origin")
    _commit_files(push_repo, {"p.md": b"fine\n"}, TERM_MESSAGE)
    if on_remote:
        _git(push_repo, "push", "-q", "origin", "main")
    _push(monkeypatch, "origin", _commit_files(push_repo, {"q.md": b"fine\n"}, "feat: add q"))
    assert _pre_push(push_repo) == (0 if on_remote else 1)


@pytest.mark.parametrize(
    ("data", "expected"), [(TERM_TEXT, 1), (b"fine\n", 0)], ids=["term", "clean"]
)
def test_pre_push_to_a_remote_not_named_origin_scans_normally(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch, *, data: bytes, expected: int
) -> None:
    _git(push_repo, "update-ref", "-d", "refs/remotes/origin/main")  # no origin/main anywhere
    _remote(push_repo, "upstream")
    _push(monkeypatch, "upstream", _commit_files(push_repo, {"n.md": data}, "feat: add n"))
    assert _pre_push(push_repo) == expected


def test_pre_push_counts_a_commit_only_another_remote_holds_as_new(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(push_repo, "update-ref", "-d", "refs/remotes/origin/main")
    _remote(push_repo, "upstream")
    _remote(push_repo, "mirror")
    _commit_files(push_repo, {"notes.md": TERM_TEXT}, "feat: add notes")
    _git(push_repo, "push", "-q", "mirror", "main")  # only the mirror holds the term commit
    pushed = _commit_files(push_repo, {"q.md": b"fine\n"}, "feat: add q")
    _push(monkeypatch, "upstream", pushed)
    assert _pre_push(push_repo) == 1  # upstream lacks it
    _push(monkeypatch, "mirror", pushed)
    assert _pre_push(push_repo) == 0  # the mirror has it
    # a manual run names no remote: a commit any remote-tracking ref holds is published
    for name in ("PRE_COMMIT_REMOTE_NAME", "PRE_COMMIT_TO_REF"):
        monkeypatch.delenv(name)
    assert _pre_push(push_repo) == 0


def test_pre_push_reads_what_a_merge_adds_beyond_its_parents(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _remote(push_repo, "origin")
    _branch_x(push_repo, {"x.md": b"fine\n"}, "feat: add x")
    _commit_files(push_repo, {"m.md": b"fine\n"}, "feat: add m")
    _git(push_repo, "merge", "-q", "--no-ff", "--no-commit", "x")
    (push_repo / "evil.md").write_bytes(TERM_TEXT)  # in neither parent
    _git(push_repo, "add", "evil.md")
    _git(push_repo, "commit", "-q", "-m", "chore: merge x")
    _push(monkeypatch, "origin", _git(push_repo, "rev-parse", "HEAD"))
    assert _pre_push(push_repo) == 1
    short = _git(push_repo, "rev-parse", "--short", "HEAD")
    assert (
        capsys.readouterr().err.splitlines()[0] == f"{short}:evil.md:1: matches denylist pattern #2"
    )


@pytest.mark.parametrize("on_remote", [False, True], ids=["remote-lacks-x", "remote-has-x"])
def test_pre_push_does_not_rescan_what_a_merge_takes_from_a_parent(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch, *, on_remote: bool
) -> None:
    _remote(push_repo, "origin")
    _branch_x(push_repo, {"notes.md": TERM_TEXT}, "feat: add notes")
    if on_remote:
        _git(push_repo, "push", "-q", "origin", "x")
    _commit_files(push_repo, {"m.md": b"fine\n"}, "feat: add m")
    _git(push_repo, "merge", "-q", "--no-ff", "-m", "chore: merge x", "x")
    _push(monkeypatch, "origin", _git(push_repo, "rev-parse", "HEAD"))
    assert _pre_push(push_repo) == (0 if on_remote else 1)


def test_pre_push_reports_a_failing_git_in_one_line(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _push(monkeypatch, "origin", "1" * 40)  # no such object
    assert _pre_push(push_repo) == 1
    assert capsys.readouterr().err.splitlines() == [
        "check-public-tree: git rev-list failed, refusing"
    ]


@pytest.mark.usefixtures("push_repo")
def test_a_missing_blob_fails_closed_instead_of_reading_as_empty() -> None:
    with pytest.raises(cpt.GitError, match="cat-file"):
        cpt.read_blobs(["1" * 40])


def test_diff_tree_output_it_cannot_parse_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cpt, "git_out", lambda *_args, **_kw: b"not-a-record\0path\0")
    with pytest.raises(cpt.GitError, match="diff-tree"):
        cpt.changes("HEAD")


def test_push_report_takes_its_inputs_as_arguments_not_from_the_environment(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pushed = _commit_files(push_repo, {"n.md": TERM_TEXT, ".claude/x": b"fine\n"}, "feat: add n")
    short = _git(push_repo, "rev-parse", "--short", pushed)
    monkeypatch.setenv("PRE_COMMIT_REMOTE_NAME", "nowhere")
    monkeypatch.setenv("PRE_COMMIT_LOCAL_BRANCH", "refs/heads/secretproject")
    clean_ref = {"local ref": "refs/heads/feature"}
    assert cpt.push_report("origin", pushed, clean_ref, PATTERNS) == [
        f"{short}:.claude/x: {PRIVATE_PATH_FINDING}",
        f"{short}:n.md:1: matches denylist pattern #2",
    ]
    assert cpt.push_report("origin", pushed, {"remote ref": "refs/heads/secretproject"}, PATTERNS)[
        -1:
    ] == ["ref remote ref: matches denylist pattern #2"]
    # without a denylist only the path guard runs
    assert cpt.push_report("origin", pushed, clean_ref, None) == [
        f"{short}:.claude/x: {PRIVATE_PATH_FINDING}"
    ]


@pytest.mark.parametrize(
    "extra", [["a.md"], ["--commit-messages", "origin/main..HEAD"], ["--message-files", "m.txt"]]
)
def test_pre_push_refuses_inputs_it_would_ignore(push_repo: Path, extra: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cpt.main(["--denylist", str(push_repo.parent / "deny.txt"), "--pre-push", *extra])
    assert exit_info.value.code == 2


# A push to the canonical repository (only writers push there) with no denylist reachable
# would publish unscanned: pre-commit hides a passing hook's skip notice and nothing runs
# CI before a branch is public. Public contributors push to forks and keep the skip.
CANONICAL_URLS = [
    "https://github.com/Prism-Purpose-Pace/milchglas",
    "https://github.com/Prism-Purpose-Pace/milchglas.git",
    "https://github.com/Prism-Purpose-Pace/milchglas/",
    "https://github.com/Prism-Purpose-Pace/milchglas.git/",
    "git@github.com:Prism-Purpose-Pace/milchglas",
    "git@github.com:Prism-Purpose-Pace/milchglas.git",
    "ssh://git@github.com/Prism-Purpose-Pace/milchglas",
    "ssh://git@github.com/Prism-Purpose-Pace/milchglas.git",
    "https://GitHub.com/prism-purpose-pace/MILCHGLAS.git",
    # Forms a hand-written list misses: a token in the URL, a port, http, no ssh user, a
    # mirror host. Matching the path tail makes an unknown form refuse instead of skip.
    "https://x-access-token:t0ken@github.com/Prism-Purpose-Pace/milchglas.git",
    "ssh://git@github.com:22/Prism-Purpose-Pace/milchglas.git",
    "http://github.com/Prism-Purpose-Pace/milchglas",
    "ssh://github.com/Prism-Purpose-Pace/milchglas.git",
    "git@gitlab.com:Prism-Purpose-Pace/milchglas.git",
    # Non-normalised forms that GitHub resolves to the same repository (git ls-remote): a
    # doubled slash, a dot segment, a parent segment. The path is normalised before the match.
    "https://github.com/Prism-Purpose-Pace/milchglas.git//",
    "https://github.com/Prism-Purpose-Pace//milchglas.git",
    "https://github.com/Prism-Purpose-Pace/./milchglas.git",
    "https://github.com/Prism-Purpose-Pace/milchglas.git/.",
    "https://github.com/Prism-Purpose-Pace/x/../milchglas.git",
    "git@github.com:Prism-Purpose-Pace/./milchglas.git",
]
NOT_CANONICAL_URLS = [
    "https://github.com/someone/milchglas.git",
    "https://github.com/Prism-Purpose-Pace/milchglas-fork",
    "https://github.com/Prism-Purpose-Pace/milchglas.git.evil",
    "https://github.com/Prism-Purpose-Pace/milchglas/extra",
    "https://github.com/other-Prism-Purpose-Pace/milchglas.git",
    "https://github.com/Prism-Purpose-Pace/milchglas/../other.git",
    "/srv/git/milchglas.git",
    "",
]
NOT_CANONICAL_IDS = [
    "fork",
    "name-suffix",
    "name-trailing-text",
    "extra-path",
    "owner-prefix",
    "parent-segment-to-another-repo",
    "local-path",
    "empty",
]


def _pre_push_without_denylist(repo: Path) -> int:
    # PUBLIC_DENYLIST is unset (push_repo), the file is absent and the tmp repo has no
    # .claude/context/ for the main-checkout fallback to find.
    return cpt.main(["--denylist", str(repo.parent / "absent.txt"), "--pre-push"])


@pytest.mark.parametrize("url", CANONICAL_URLS)
def test_pre_push_to_the_canonical_repository_refuses_without_a_denylist(
    push_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    url: str,
) -> None:
    monkeypatch.setenv("PRE_COMMIT_REMOTE_URL", url)
    assert _pre_push_without_denylist(push_repo) == 2
    err = capsys.readouterr().err
    assert "PUBLIC_DENYLIST" in err
    assert str(cpt.DEFAULT_DENYLIST) in err
    assert "term scan skipped" not in err


@pytest.mark.parametrize("url", NOT_CANONICAL_URLS, ids=NOT_CANONICAL_IDS)
def test_pre_push_to_another_remote_keeps_the_skip_without_a_denylist(
    push_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    url: str,
) -> None:
    monkeypatch.setenv("PRE_COMMIT_REMOTE_URL", url)
    assert _pre_push_without_denylist(push_repo) == 0
    assert "term scan skipped" in capsys.readouterr().err


def test_manual_pre_push_run_without_a_remote_keeps_the_skip_without_a_denylist(
    push_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _pre_push_without_denylist(push_repo) == 0  # PRE_COMMIT_REMOTE_URL unset
    assert "term scan skipped" in capsys.readouterr().err


def test_pre_push_to_the_canonical_repository_passes_with_a_denylist_and_a_clean_tree(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRE_COMMIT_REMOTE_URL", CANONICAL_URLS[1])
    assert _pre_push(push_repo) == 0
    _commit_files(push_repo, {"head.md": TERM_TEXT}, "feat: add head")
    assert _pre_push(push_repo) == 1  # the denylist is read and still guards


def test_commit_stage_without_a_denylist_keeps_the_skip_for_the_canonical_remote(
    push_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Only the push refuses: a commit has no remote, and a contributor commit stays unblocked.
    monkeypatch.setenv("PRE_COMMIT_REMOTE_URL", CANONICAL_URLS[1])
    assert cpt.main(["--denylist", str(push_repo.parent / "absent.txt"), "README.md"]) == 0
    assert "term scan skipped" in capsys.readouterr().err


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


# --pre-push-refs: the legacy pre-push entry (scripts/install_push_guard.py). pre-commit reads
# git's pre-push stdin itself and hands hooks at most the first ref with new commits; a push
# whose refs carry no new commit runs no hook at all, so a ref name, refs 2..n and an annotated
# tag's own message were published unscanned. This mode reads git's own list, every line.
# A deletion line (all-zero local sha) publishes nothing new: neither ref name is scanned.
NULL_OBJECT = "0" * 40
REMOTE_URL = "/srv/git/elsewhere.git"  # not the canonical repository


def _line(local_ref: str, sha: str, remote_ref: str | None = None) -> str:
    return f"{local_ref} {sha} {remote_ref or local_ref} {NULL_OBJECT}\n"


def _pre_push_refs(
    repo: Path, monkeypatch: pytest.MonkeyPatch, *lines: str, url: str = REMOTE_URL
) -> int:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO("".join(lines).encode())))
    deny = str(repo.parent / "deny.txt")
    return cpt.main(["--denylist", deny, "--pre-push-refs", "origin", url])


def _new_branch(repo: Path, name: str, files: dict[str, bytes], message: str) -> str:
    """Commit on a new branch off main, then back on main; return the commit."""
    _git(repo, "checkout", "-q", "-b", name, "main")
    sha = _commit_files(repo, files, message)
    _git(repo, "checkout", "-q", "main")
    return sha


@pytest.fixture
def remote_repo(push_repo: Path) -> Path:
    """push_repo whose commit the bare remote `origin` already holds."""
    _remote(push_repo, "origin")
    return push_repo


def test_pre_push_refs_reads_a_ref_name_that_carries_no_new_commit(
    remote_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    head = _git(remote_repo, "rev-parse", "HEAD")
    _git(remote_repo, "branch", "secretproject-x")  # the remote already has this commit
    assert _pre_push_refs(remote_repo, monkeypatch, _line("refs/heads/secretproject-x", head)) == 1
    err = capsys.readouterr().err
    assert err.splitlines() == [
        "ref local ref 1: matches denylist pattern #2",
        "ref remote ref 1: matches denylist pattern #2",
        "check-public-tree: 2 finding(s)",
    ]
    assert "secretproject" not in err.lower()


def test_pre_push_refs_passes_a_clean_ref_name_that_carries_no_new_commit(
    remote_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    head = _git(remote_repo, "rev-parse", "HEAD")
    _git(remote_repo, "branch", "feature-x")
    assert _pre_push_refs(remote_repo, monkeypatch, _line("refs/heads/feature-x", head)) == 0
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("second", ["ref-name", "new-commit"])
def test_pre_push_refs_reads_every_line_not_only_the_first(
    remote_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    second: str,
) -> None:
    first = _new_branch(remote_repo, "a", {"a.md": b"fine\n"}, "feat: add a")
    if second == "ref-name":
        branch = "secretproject-b"
        _git(remote_repo, "branch", branch)
        pushed = _git(remote_repo, "rev-parse", "HEAD")
        expected = [
            "ref local ref 2: matches denylist pattern #2",
            "ref remote ref 2: matches denylist pattern #2",
            "check-public-tree: 2 finding(s)",
        ]
    else:
        branch = "b"
        pushed = _new_branch(remote_repo, "b", {"b.md": b"fine\n"}, TERM_MESSAGE)
        short = _git(remote_repo, "rev-parse", "--short", pushed)
        expected = [
            f"commit {short}:3: matches denylist pattern #2",
            "check-public-tree: 1 finding(s)",
        ]
    lines = (_line("refs/heads/a", first), _line(f"refs/heads/{branch}", pushed))
    assert _pre_push_refs(remote_repo, monkeypatch, *lines) == 1
    err = capsys.readouterr().err
    assert err.splitlines() == expected
    assert "secretproject" not in err.lower()


def test_pre_push_refs_passes_two_clean_lines(
    remote_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _new_branch(remote_repo, "a", {"a.md": b"fine\n"}, "feat: add a")
    second = _new_branch(remote_repo, "b", {"b.md": b"fine\n"}, "feat: add b")
    lines = (_line("refs/heads/a", first), _line("refs/heads/b", second))
    assert _pre_push_refs(remote_repo, monkeypatch, *lines) == 0


def _tag(repo: Path, name: str, message: str, target: str = "HEAD") -> str:
    _git(repo, "tag", "-a", name, "-m", message, target)
    return _git(repo, "rev-parse", f"refs/tags/{name}")  # the tag object, not the commit


def test_pre_push_refs_reads_an_annotated_tags_own_message(
    remote_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tag = _tag(remote_repo, "v1", "about secretproject")  # the commit is on the remote
    assert _pre_push_refs(remote_repo, monkeypatch, _line("refs/tags/v1", tag)) == 1
    err = capsys.readouterr().err
    assert err.splitlines() == [
        f"tag {tag[:12]}:6: matches denylist pattern #2",
        "check-public-tree: 1 finding(s)",
    ]
    assert "secretproject" not in err.lower()


def test_pre_push_refs_passes_an_annotated_tag_with_a_clean_message(
    remote_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tag = _tag(remote_repo, "v1", "release one")
    assert _pre_push_refs(remote_repo, monkeypatch, _line("refs/tags/v1", tag)) == 0


def test_pre_push_refs_reads_each_tag_of_a_chain(
    remote_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tag(remote_repo, "inner", "about secretproject")
    outer = _tag(remote_repo, "outer", "release one", "refs/tags/inner")
    assert "type tag" in _git(remote_repo, "cat-file", "-p", outer)  # a tag of a tag
    assert _pre_push_refs(remote_repo, monkeypatch, _line("refs/tags/outer", outer)) == 1


def test_pre_push_refs_reads_the_commit_a_tag_peels_to(
    remote_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pushed = _new_branch(remote_repo, "x", {"notes.md": TERM_TEXT}, "feat: add notes")
    tag = _tag(remote_repo, "v2", "release two", pushed)
    assert _pre_push_refs(remote_repo, monkeypatch, _line("refs/tags/v2", tag)) == 1
    assert f"{pushed[:7]}:notes.md:1: matches denylist pattern #2" in capsys.readouterr().err


def test_pre_push_refs_refuses_a_tag_on_a_tree_it_cannot_scan(
    remote_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tag = _tag(remote_repo, "t", "release one", "HEAD^{tree}")
    assert _pre_push_refs(remote_repo, monkeypatch, _line("refs/tags/t", tag)) == 1
    assert "pushes a tree, which cannot be scanned" in capsys.readouterr().err


def test_pre_push_refs_ignores_a_deletion_line(
    remote_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    head = _git(remote_repo, "rev-parse", "HEAD")
    gone = f"(delete) {NULL_OBJECT} refs/heads/secretproject-x {head}\n"
    assert _pre_push_refs(remote_repo, monkeypatch, gone) == 0
    assert capsys.readouterr().err == ""


def test_pre_push_refs_with_no_line_has_nothing_to_scan(
    remote_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _pre_push_refs(remote_repo, monkeypatch) == 0


@pytest.mark.parametrize("line", ["refs/heads/x\n", "a b c d e\n"], ids=["short", "long"])
def test_pre_push_refs_refuses_a_line_it_cannot_parse(
    remote_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    line: str,
) -> None:
    assert _pre_push_refs(remote_repo, monkeypatch, line) == 1
    assert "push line 1: cannot be parsed, refusing" in capsys.readouterr().err


def test_pre_push_refs_refuses_an_object_the_clone_does_not_hold(
    remote_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _pre_push_refs(remote_repo, monkeypatch, _line("refs/heads/x", "1" * 40)) == 1
    assert "git cat-file failed, refusing" in capsys.readouterr().err


def test_pre_push_refs_refuses_a_tag_object_without_an_object_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = {"-t": b"tag\n", "tag": b"tagger Dev <dev@example.org> 0 +0000\n\nmessage\n"}
    monkeypatch.setattr(cpt, "git_out", lambda *args, **_kw: outputs[args[1]])
    with pytest.raises(cpt.GitError, match="cat-file"):
        cpt.peel_tags("a" * 40, PATTERNS)


def test_pre_push_refs_without_a_denylist_skips_the_tag_scan_and_keeps_the_path_guard(
    remote_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tag = _tag(remote_repo, "v1", "about secretproject")
    monkeypatch.setattr(
        sys, "stdin", io.TextIOWrapper(io.BytesIO(_line("refs/tags/v1", tag).encode()))
    )
    absent = str(remote_repo.parent / "absent.txt")
    assert cpt.main(["--denylist", absent, "--pre-push-refs", "origin", REMOTE_URL]) == 0
    assert "term scan skipped" in capsys.readouterr().err
    pushed = _new_branch(remote_repo, "x", {".claude/x": b"fine\n"}, "feat: add x")
    monkeypatch.setattr(
        sys, "stdin", io.TextIOWrapper(io.BytesIO(_line("refs/heads/x", pushed).encode()))
    )
    assert cpt.main(["--denylist", absent, "--pre-push-refs", "origin", REMOTE_URL]) == 1
    assert PRIVATE_PATH_FINDING in capsys.readouterr().err


def test_pre_push_refs_reports_a_finding_once_when_two_lines_share_it(
    remote_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pushed = _new_branch(remote_repo, "x", {"notes.md": TERM_TEXT}, "feat: add notes")
    lines = (_line("refs/heads/x", pushed), _line("refs/heads/y", pushed))
    assert _pre_push_refs(remote_repo, monkeypatch, *lines) == 1
    assert capsys.readouterr().err.count("notes.md:1:") == 1


@pytest.mark.parametrize("url", CANONICAL_URLS)
def test_pre_push_refs_to_the_canonical_repository_refuses_without_a_denylist(
    push_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    url: str,
) -> None:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"")))
    args = ["--denylist", str(push_repo.parent / "absent.txt"), "--pre-push-refs", "origin", url]
    assert cpt.main(args) == 2
    err = capsys.readouterr().err
    assert "PUBLIC_DENYLIST" in err
    assert "term scan skipped" not in err


@pytest.mark.parametrize("url", NOT_CANONICAL_URLS, ids=NOT_CANONICAL_IDS)
def test_pre_push_refs_to_another_remote_keeps_the_skip_without_a_denylist(
    push_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    url: str,
) -> None:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"")))
    args = ["--denylist", str(push_repo.parent / "absent.txt"), "--pre-push-refs", "origin", url]
    assert cpt.main(args) == 0
    assert "term scan skipped" in capsys.readouterr().err


@pytest.mark.parametrize(
    "extra",
    [["a.md"], ["--pre-push"], ["--commit-messages", "HEAD"], ["--message-files", "m.txt"]],
)
def test_pre_push_refs_refuses_inputs_it_would_ignore(
    push_repo: Path, capsys: pytest.CaptureFixture[str], extra: list[str]
) -> None:
    deny = str(push_repo.parent / "deny.txt")
    with pytest.raises(SystemExit) as exit_info:
        cpt.main(["--denylist", deny, "--pre-push-refs", "origin", REMOTE_URL, *extra])
    assert exit_info.value.code == 2
    # the mode's own refusal, not argparse failing on an unknown flag
    assert "--pre-push-refs reads git's push lines and takes no paths" in capsys.readouterr().err


def test_pre_push_refs_needs_a_remote_name_and_url(
    push_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cpt.main(["--denylist", str(push_repo.parent / "deny.txt"), "--pre-push-refs", "origin"])
    assert exit_info.value.code == 2
    assert "expected 2 arguments" in capsys.readouterr().err


# End to end: the installer writes the shim, a stand-in for pre-commit's generated hook runs
# it as pre-push.legacy (pre-commit's `_run_legacy` runs it first with git's argv and stdin
# and stops the push on a non-zero exit), and a real `git push` is refused or lands.
STAND_IN = """#!/usr/bin/env python3
# File generated by pre-commit: https://pre-commit.com
# Stand-in for the one step of pre-commit's hook that matters here (hook_impl._run_legacy).
# Like hook-tmpl it passes --hook-dir, the flag that makes pre-commit run the legacy hook.
import os
import subprocess
import sys

legacy = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pre-push.legacy")
sys.exit(subprocess.run([legacy, *sys.argv[1:]], check=False).returncode)
"""
TEST_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "PUBLIC_DENYLIST": "\n".join(p.pattern for p in PATTERNS),
}


def _install_guard(repo: Path) -> None:
    """The versioned scripts into the tmp repo, the stand-in hook, then the real installer."""
    (repo / "scripts").mkdir()
    for name in ("check_public_tree.py", "check_push_ancestry.py"):
        shutil.copy(REPO / "scripts" / name, repo / "scripts" / name)
    hook = repo / ".git/hooks/pre-push"
    hook.write_text(STAND_IN, encoding="utf-8")
    hook.chmod(0o755)
    installer = REPO / "scripts/install_push_guard.py"
    subprocess.run(
        [sys.executable, str(installer)], cwd=repo, env={**os.environ, **TEST_ENV}, check=True
    )


def _git_push(repo: Path, *refs: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), "push", "-q", "origin", *refs],
        capture_output=True,
        text=True,
        env={**os.environ, **TEST_ENV},
        check=False,
    )


def _remote_has(repo: Path, ref: str) -> bool:
    bare = repo.parent / "origin.git"
    result = subprocess.run(
        ["git", "-C", str(bare), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def test_a_real_push_of_a_term_named_branch_without_a_new_commit_is_refused(
    remote_repo: Path,
) -> None:
    _install_guard(remote_repo)
    _git(remote_repo, "branch", "secretproject-x")  # a commit the remote already has
    result = _git_push(remote_repo, "secretproject-x")
    assert result.returncode == 1
    assert "matches denylist pattern #2" in result.stderr
    assert "secretproject" not in result.stderr.lower()
    assert not _remote_has(remote_repo, "refs/heads/secretproject-x")


def test_a_real_push_of_a_clean_branch_without_a_new_commit_lands(remote_repo: Path) -> None:
    _install_guard(remote_repo)
    _git(remote_repo, "branch", "feature-x")
    assert _git_push(remote_repo, "feature-x").returncode == 0
    assert _remote_has(remote_repo, "refs/heads/feature-x")


def test_a_real_multi_ref_push_is_refused_for_a_term_in_the_second_ref(
    remote_repo: Path,
) -> None:
    _install_guard(remote_repo)
    _new_branch(remote_repo, "a", {"a.md": b"fine\n"}, "feat: add a")
    _new_branch(remote_repo, "b", {"b.md": b"fine\n"}, TERM_MESSAGE)
    result = _git_push(remote_repo, "a", "b")
    assert result.returncode == 1
    assert not _remote_has(remote_repo, "refs/heads/a")
    assert not _remote_has(remote_repo, "refs/heads/b")


def test_a_real_push_of_an_annotated_tag_with_a_term_is_refused(remote_repo: Path) -> None:
    _install_guard(remote_repo)
    _tag(remote_repo, "v1", "about secretproject")
    assert _git_push(remote_repo, "v1").returncode == 1
    assert not _remote_has(remote_repo, "refs/tags/v1")


@pytest.mark.parametrize("missing", ["uv", "script"])
def test_the_shim_refuses_in_one_line_when_uv_or_the_script_is_missing(
    remote_repo: Path, tmp_path: Path, missing: str
) -> None:
    _install_guard(remote_repo)
    if missing == "script":
        (remote_repo / "scripts/check_public_tree.py").unlink()
    git = shutil.which("git")
    assert git is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(git)
    if missing == "script":
        uv = shutil.which("uv")
        assert uv is not None
        (bin_dir / "uv").symlink_to(uv)
    shim = remote_repo / ".git/hooks/pre-push.legacy"
    result = subprocess.run(
        [sys.executable, str(shim), "origin", REMOTE_URL],
        cwd=remote_repo,
        capture_output=True,
        text=True,
        env={"PATH": str(bin_dir)},
        input="",
        check=False,
    )
    assert result.returncode == 1
    assert len(result.stderr.splitlines()) == 1
    assert "refusing the push" in result.stderr
