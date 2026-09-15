"""check_public_tree.py: private paths and denylisted terms never reach the public tree."""

from pathlib import Path

import pytest

import check_public_tree as cpt

PATTERNS = cpt.compile_patterns([r"acme\.example", r"\bsecretproject\b"])


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


def test_missing_denylist_yields_none(tmp_path: Path) -> None:
    assert cpt.load_denylist(tmp_path / "absent.txt", {}) is None


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
