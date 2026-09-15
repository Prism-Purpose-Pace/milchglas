"""check_push_ancestry.py: only history that descends from the public root may be pushed."""

import pytest

import check_push_ancestry as cpa

PUSHED = "a" * 40


def test_ref_descending_from_the_public_root_may_be_pushed() -> None:
    assert cpa.refusal(PUSHED, lambda _root, _ref: True) is None


def test_ref_outside_the_public_history_is_refused() -> None:
    message = cpa.refusal(PUSHED, lambda _root, _ref: False)
    assert message is not None
    assert PUSHED[:12] in message
    assert cpa.PUBLIC_ROOT[:12] in message


@pytest.mark.parametrize("to_ref", [None, "", "0" * 40])
def test_missing_or_deleted_ref_is_not_checked(to_ref: str | None) -> None:
    def refuse(_root: str, _ref: str) -> bool:
        raise AssertionError

    assert cpa.refusal(to_ref, refuse) is None


def test_main_reads_the_pushed_ref_from_pre_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRE_COMMIT_TO_REF", PUSHED)
    assert cpa.main(is_ancestor=lambda _root, _ref: True) == 0
    assert cpa.main(is_ancestor=lambda _root, _ref: False) == 1


@pytest.mark.parametrize("local_ref", ["refs/heads/old-branch", "refs/tags/v0.0.9"])
def test_new_ref_without_to_ref_is_resolved_from_the_local_ref(
    monkeypatch: pytest.MonkeyPatch, local_ref: str
) -> None:
    # pre-commit exports no PRE_COMMIT_TO_REF when the pushed history is new to the remote.
    monkeypatch.delenv("PRE_COMMIT_TO_REF", raising=False)
    monkeypatch.setenv("PRE_COMMIT_REMOTE_NAME", "origin")
    monkeypatch.setenv("PRE_COMMIT_LOCAL_BRANCH", local_ref)
    checked: list[str] = []

    def outside(_root: str, ref: str) -> bool:
        checked.append(ref)
        return False

    assert cpa.main(is_ancestor=outside, resolve=lambda _ref: PUSHED) == 1
    assert checked == [PUSHED]


def test_push_without_any_ref_information_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRE_COMMIT_TO_REF", raising=False)
    monkeypatch.delenv("PRE_COMMIT_LOCAL_BRANCH", raising=False)
    monkeypatch.setenv("PRE_COMMIT_REMOTE_NAME", "origin")
    assert cpa.main(is_ancestor=lambda _root, _ref: True, resolve=lambda _ref: None) == 1


def test_manual_gate_run_outside_a_push_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PRE_COMMIT_TO_REF", "PRE_COMMIT_LOCAL_BRANCH", "PRE_COMMIT_REMOTE_NAME"):
        monkeypatch.delenv(name, raising=False)
    assert cpa.main(is_ancestor=lambda _root, _ref: False, resolve=lambda _ref: None) == 0
