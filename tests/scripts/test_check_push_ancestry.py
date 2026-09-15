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
