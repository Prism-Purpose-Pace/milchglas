"""The judge runner of D-18: request shape, answer parsing, changed files, calibration (S1).

Catalogue GATE-23.

No test calls the Messages API: a fake `send` stands in for it, so the suite runs in CI
without a key. The real tree's calibration set is checked for its form and size here; the
calibration itself runs by hand (`--calibrate`), never in pytest.
"""

import io
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

import judge_features as jf
from tests.meta.test_feature_lint import check, read
from tests.scripts.test_check_public_tree import _git

if TYPE_CHECKING:
    from gherkin.parser_types import Feature

RUBRIC = {"judge-a": "Flag: rule a."}


def answer(*items: tuple[str, int, str], stop: str = "end_turn") -> dict[str, Any]:
    listed = [{"judge": name, "line": line, "reason": reason} for name, line, reason in items]
    text = json.dumps({"findings": listed})
    return {
        "stop_reason": stop,
        "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": text}],
    }


# --- the rubric and the request ------------------------------------------------------------


def test_rubric_file_names_the_four_judges_of_d18() -> None:
    rubric = jf.rubrics((jf.ROOT / jf.RUBRIC).read_text(encoding="utf-8"))
    assert set(rubric) == {"judge-solution", "judge-then", "judge-values", "judge-brief"}
    assert all("Flag:" in text and "Leave alone:" in text for text in rubric.values())


def test_rubric_without_a_judge_section_fails() -> None:
    with pytest.raises(jf.JudgeError, match="no `## judge-<name>` section"):
        jf.rubrics("# Rubrics\n\n## Notes\nnothing\n")


def test_request_numbers_the_lines_and_pins_the_schema_to_the_judges() -> None:
    body = jf.request("Feature: x\n  A sample.\n", RUBRIC)
    assert body["model"] == jf.MODEL
    assert body["messages"] == [{"role": "user", "content": "   1| Feature: x\n   2|   A sample."}]
    assert "Flag: rule a." in body["system"]
    schema = body["output_config"]["format"]["schema"]
    assert schema["properties"]["findings"]["items"]["properties"]["judge"]["enum"] == ["judge-a"]
    assert not {"temperature", "top_p", "top_k", "fallbacks"} & body.keys()


# --- the answer ----------------------------------------------------------------------------


def test_finding_comes_from_the_text_block_and_names_file_line_judge() -> None:
    [finding] = jf.findings("f.feature", answer(("judge-a", 3, "a mechanism")), ["judge-a"])
    assert str(finding) == "f.feature:3: judge-a: a mechanism"


def test_finding_of_a_judge_outside_the_rubric_is_dropped() -> None:
    assert jf.findings("f", answer(("judge-z", 1, "x")), ["judge-a"]) == []


@pytest.mark.parametrize("stop", ["refusal", "max_tokens", None])
def test_answer_without_end_turn_is_no_verdict(stop: str | None) -> None:
    with pytest.raises(jf.JudgeError, match="no verdict"):
        jf.findings("f", answer(stop=str(stop)) | {"stop_reason": stop}, ["judge-a"])


def test_answer_that_is_no_findings_list_fails() -> None:
    broken = {"stop_reason": "end_turn", "content": [{"type": "text", "text": "fine"}]}
    with pytest.raises(jf.JudgeError, match="no findings list"):
        jf.findings("f", broken, ["judge-a"])


# --- the HTTP call -------------------------------------------------------------------------


class Opener:
    def __init__(
        self, reply: bytes = b'{"stop_reason": "end_turn"}', error: Exception | None = None
    ) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[tuple[urllib.request.Request, float]] = []

    def __call__(self, call: urllib.request.Request, timeout: float) -> io.BytesIO:
        self.calls.append((call, timeout))
        if self.error:
            raise self.error
        return io.BytesIO(self.reply)


def test_post_sends_key_version_and_body_to_the_messages_api() -> None:
    opener = Opener()
    assert jf.post({"model": "m"}, key="secret-key", opener=opener) == {"stop_reason": "end_turn"}
    [(call, timeout)] = opener.calls
    assert timeout == 600
    assert (call.full_url, call.get_method()) == (jf.API, "POST")
    assert call.get_header("X-api-key") == "secret-key"
    assert call.get_header("Anthropic-version") == jf.VERSION
    assert json.loads(cast("bytes", call.data)) == {"model": "m"}


def test_http_error_names_the_status_but_never_the_key() -> None:
    error = urllib.error.HTTPError(jf.API, 401, "no", {}, io.BytesIO(b'{"error": "bad key"}'))  # type: ignore[arg-type]
    with pytest.raises(jf.JudgeError, match="401") as raised:
        jf.post({}, key="secret-key", opener=Opener(error=error))
    assert "secret-key" not in str(raised.value)


def test_unreachable_api_fails() -> None:
    with pytest.raises(jf.JudgeError, match="unreachable"):
        jf.post({}, key="k", opener=Opener(error=urllib.error.URLError("offline")))


# --- judging files -------------------------------------------------------------------------


def flag_when(pattern: str, judge: str = "judge-a") -> jf.Post:
    """A fake model: one finding on line 1 when the file text matches `pattern`."""

    def send(body: dict[str, Any]) -> dict[str, Any]:
        text = body["messages"][0]["content"]
        return answer((judge, 1, "seeded")) if re.search(pattern, text) else answer()

    return send


def test_judge_reports_each_file_that_the_model_flags(tmp_path: Path) -> None:
    (tmp_path / "a.feature").write_text("Feature: flagged\n", encoding="utf-8")
    (tmp_path / "b.feature").write_text("Feature: fine\n", encoding="utf-8")
    paths = sorted(tmp_path.glob("*.feature"))
    found = jf.judge(paths, RUBRIC, flag_when("flagged"))
    assert [str(f) for f in found] == [f"{tmp_path.as_posix()}/a.feature:1: judge-a: seeded"]


def repo(tmp_path: Path) -> Path:
    for name in ("a", "b", "c"):
        path = tmp_path / "tests/features" / f"{name}.feature"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"Feature: {name}\n", encoding="utf-8")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def test_changed_files_are_the_edited_and_new_features_since_main(tmp_path: Path) -> None:
    root = repo(tmp_path)
    _git(root, "switch", "-q", "-c", "topic")
    features = root / "tests/features"
    (features / "a.feature").write_text("Feature: a changed\n", encoding="utf-8")
    (features / "b.feature").unlink()
    (features / "d.feature").write_text("Feature: d\n", encoding="utf-8")
    (features / "notes.txt").write_text("no feature\n", encoding="utf-8")
    assert jf.changed(root) == [features / "a.feature", features / "d.feature"]


def test_changed_files_without_main_fail(tmp_path: Path) -> None:
    root = repo(tmp_path)
    _git(root, "branch", "-q", "-m", "main", "topic")
    with pytest.raises(jf.JudgeError, match="neither origin/main nor main"):
        jf.changed(root)


# --- calibration (S1) ----------------------------------------------------------------------


def seeds(tmp_path: Path, defects: int, clean: int) -> Path:
    for n in range(1, defects + 1):
        (tmp_path / f"judge-a--defect-{n:02}.feature").write_text(f"Feature: defect {n}\n", "utf-8")
    for n in range(1, clean + 1):
        (tmp_path / f"clean-{n:02}.feature").write_text(f"Feature: clean {n}\n", "utf-8")
    return tmp_path


def numbers(last: int) -> str:
    return "|".join(str(n) for n in range(1, last + 1))


@pytest.mark.parametrize(
    ("defects", "found", "false", "passed"),
    [
        (30, 26, 3, True),
        (30, 25, 0, False),
        (30, 30, 4, False),
        (29, 29, 0, False),
        (60, 52, 0, True),
        (60, 51, 0, False),
    ],
    ids=[
        "at-the-bar",
        "one-defect-short",
        "one-false-too-many",
        "too-few-seeds",
        "ratio",
        "ratio-short",
    ],
)
def test_calibration_passes_only_at_26_of_30_found_and_3_of_30_false(
    tmp_path: Path, defects: int, found: int, false: int, *, passed: bool
) -> None:
    folder = seeds(tmp_path, defects, 30)
    flagged = rf"Feature: (defect ({numbers(found)})|clean ({numbers(false) or 'none'}))$"
    lines, ok = jf.calibrate(folder, RUBRIC, flag_when(flagged))
    assert ok is passed
    assert lines == [
        f"judge-a: {found}/{defects} defects found, {false}/30 clean files flagged: "
        + ("pass" if passed else "FAIL (needs 26/30 found, at most 3/30 false)")
    ]


@pytest.mark.parametrize("name", ["other.feature", "judge-z--defect-01.feature", "clean.feature"])
def test_calibration_refuses_a_file_without_a_known_label(tmp_path: Path, name: str) -> None:
    (seeds(tmp_path, 1, 1) / name).write_text("Feature: x\n", encoding="utf-8")
    with pytest.raises(jf.JudgeError, match=r"not <judge>--defect-NN\.feature"):
        jf.calibrate(tmp_path, RUBRIC, flag_when("never"))


# --- the command ---------------------------------------------------------------------------


def test_command_without_a_key_fails_and_says_why(capsys: pytest.CaptureFixture[str]) -> None:
    assert jf.main(["x.feature"], environ={}) == 2
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


def test_command_prints_findings_and_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "a.feature"
    path.write_text("Feature: flagged\n", encoding="utf-8")
    assert jf.main([str(path)], send=flag_when("flagged", "judge-then")) == 0
    assert capsys.readouterr().out == f"{path.as_posix()}:1: judge-then: seeded\n"


def test_command_fails_a_judge_below_the_bar(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = seeds(tmp_path, 0, 0)
    (folder / "judge-then--defect-01.feature").write_text("Feature: x\n", encoding="utf-8")
    assert jf.main(["--calibrate", str(folder)], send=flag_when("x", "judge-then")) == 1
    assert "judge-then: 1/1 defects found" in capsys.readouterr().out


def test_command_stops_on_a_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "a.feature"
    path.write_text("Feature: a\n", encoding="utf-8")
    assert jf.main([str(path)], send=lambda _body: answer(stop="refusal")) == 2
    assert "'refusal', no verdict" in capsys.readouterr().err


def test_section_without_a_status_fails() -> None:
    with pytest.raises(jf.JudgeError, match="no `Status: advisory` or `Status: blocking` line"):
        jf.blocking({"judge-a": "Flag: rule a."})


def test_status_line_stays_out_of_the_request() -> None:
    body = jf.request("Feature: x\n", {"judge-a": "Status: blocking\n\nFlag: rule a."})
    assert "Status:" not in body["system"]
    assert "Flag: rule a." in body["system"]


GATE_RUBRIC = """\
## judge-a

Status: blocking

Flag: rule a.

## judge-b

Status: advisory

Flag: rule b.
"""


@pytest.mark.parametrize(
    ("flagging", "code"), [("judge-a", 1), ("judge-b", 0)], ids=["blocking", "advisory"]
)
def test_push_stage_fails_only_on_a_blocking_judge(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flagging: str, code: int
) -> None:
    rubric = tmp_path / "judges.md"
    rubric.write_text(GATE_RUBRIC, encoding="utf-8")
    path = tmp_path / "a.feature"
    path.write_text("Feature: a\n", encoding="utf-8")
    send = flag_when("Feature", flagging)
    assert jf.main(["--blocking", str(path)], send=send, rubric_file=rubric) == code
    assert capsys.readouterr().out == f"{path.as_posix()}:1: {flagging}: seeded\n"


def test_push_stage_with_a_blocking_judge_needs_the_key(tmp_path: Path) -> None:
    rubric = tmp_path / "judges.md"
    rubric.write_text(GATE_RUBRIC, encoding="utf-8")
    assert jf.main(["--blocking", "a.feature"], environ={}, rubric_file=rubric) == 2


def test_push_stage_without_changed_features_needs_no_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rubric = tmp_path / "judges.md"
    rubric.write_text(GATE_RUBRIC, encoding="utf-8")
    monkeypatch.setattr(jf, "changed", lambda _root: [])
    assert jf.main(["--blocking"], environ={}, rubric_file=rubric) == 0


def test_push_stage_without_a_blocking_judge_passes_without_key_or_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rubric = tmp_path / "judges.md"
    rubric.write_text(GATE_RUBRIC.replace("Status: blocking", "Status: advisory"), "utf-8")
    assert jf.main(["--blocking", "a.feature"], environ={}, rubric_file=rubric) == 0
    assert capsys.readouterr() == ("", "")


# --- the real calibration set --------------------------------------------------------------

SET = jf.ROOT / "tests/meta/judge-set"


def test_calibration_set_holds_enough_seeds_for_every_judge() -> None:
    rubric = jf.rubrics((jf.ROOT / jf.RUBRIC).read_text(encoding="utf-8"))
    labels = [jf.SEED.fullmatch(path.name) for path in sorted(SET.glob("*.feature"))]
    assert all(labels), "every file is <judge>--defect-NN.feature or clean-NN.feature"
    counts = {name: sum(1 for m in labels if m and m[1] == name) for name in [*rubric, None]}
    assert min(counts.values()) >= jf.SEEDS, counts


def test_calibration_set_keeps_the_feature_form() -> None:
    problems: list[str] = []
    seen: dict[str, str] = {}
    for path in sorted(SET.glob("*.feature")):
        document = read(path)
        if isinstance(document, tuple):
            problems.append(f"{path.name}:{document[0]}: parse")
            continue
        problems += [str(finding) for finding in check(path.name, document)]
        feature = cast("Feature | None", document.get("feature"))  # absent from an empty file
        names = [f"name {feature['name']!r}"] if feature else []
        for key in [*re.findall(r"@id:\d+", path.read_text(encoding="utf-8")), *names]:
            if (first := seen.setdefault(key, path.name)) != path.name:
                problems.append(f"{path.name}: {key} also in {first}")
    assert problems == []
