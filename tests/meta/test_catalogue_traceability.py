"""The test catalogue and the tests must say the same thing.

Catalogue GATE-17.

`docs/test-catalogue.md` gives every pinned behaviour an ID and a status. Nothing else
reads that status, so an acceptance item could stay "planned" after its test landed, or
read "exists" with no test behind it. Three checks close that:

- unresolved: every catalogue-shaped token under `src/` and `tests/` equals a row ID, or
  a row ID plus `-` and a lowercase suffix (a fixture UID such as `<ID>-off-grid`). A range
  `<ID>..<n>` resolves when both ends are rows.
- uncited: every row with status `exists` is cited by a test.
- planned_cited: every row a test cites has status `exists`.

The areas that make a token catalogue-shaped come from the first segment of the ID column,
so a new area needs no edit here. A citation is a token in a `tests/**/*.py` file, or the
row ID lower-cased with dashes as underscores (`test_<area>_<n>`); fixtures and prose may
carry an ID that resolves but they do not count as a test. Known limit: a citation proves
a test names the row, not that the test checks the row's behaviour.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CATALOGUE = Path("docs/test-catalogue.md")
STATUSES = frozenset({"exists", "planned"})
# First cell: an ID such as AREA-3 or AREA-SUB-3; last cell: the status.
ROW = re.compile(r"^\|\s*([A-Z0-9]+(?:-[A-Z0-9]+)*-\d+)\s*\|.*\|\s*([^|]*?)\s*\|\s*$")
SUFFIX = re.compile(r"(?:-[a-z][a-z0-9]*(?:-[a-z0-9]+)*)?")

type Rows = dict[str, str]
type Problems = dict[str, list[str]]


def parse_catalogue(text: str) -> Rows:
    rows: Rows = {}
    for line in text.splitlines():
        if match := ROW.match(line):
            row_id, status = match.groups()
            if row_id in rows or status not in STATUSES:
                msg = f"{row_id}: duplicate row or status {status!r}"
                raise ValueError(msg)
            rows[row_id] = status
    if not rows:
        msg = "no catalogue rows"
        raise ValueError(msg)
    return rows


def split_id(row_id: str) -> tuple[str, int]:
    prefix, number = row_id.rsplit("-", 1)
    return prefix, int(number)


def resolve(rows: Rows, text: str) -> tuple[list[str], set[str]]:
    """The tokens of `text` that match no row, and the row IDs it cites in upper case."""
    areas = "|".join(sorted({re.escape(row_id.split("-")[0]) for row_id in rows}))
    token = re.compile(
        rf"(?<![\w-])(?P<prefix>(?:{areas})(?:-[A-Z][A-Z0-9]*)*)-(?P<lo>\d+)"
        r"(?:\.\.(?P<hi>\d+))?(?P<rest>[\w-]*)"
    )
    unresolved: list[str] = []
    cited: set[str] = set()
    for match in token.finditer(text):
        prefix, lo = match["prefix"], int(match["lo"])
        hi = int(match["hi"] or lo)
        ends = {f"{prefix}-{lo}", f"{prefix}-{hi}"}
        if lo <= hi and ends <= rows.keys() and SUFFIX.fullmatch(match["rest"]):
            cited |= {r for r in rows if (p := split_id(r))[0] == prefix and lo <= p[1] <= hi}
        else:
            unresolved.append(match[0])
    return unresolved, cited


def cited_by_name(rows: Rows, text: str) -> set[str]:
    """Row IDs written as `test_<area>_<n>`: lower case, dashes become underscores."""
    names = {row_id.lower().replace("-", "_"): row_id for row_id in rows}
    alternatives = "|".join(sorted(names, key=len, reverse=True))
    pattern = re.compile(rf"(?<![a-z0-9])({alternatives})(?![0-9])")
    return {names[match[1]] for match in pattern.finditer(text)}


def problems(root: Path) -> Problems:
    rows = parse_catalogue((root / CATALOGUE).read_text(encoding="utf-8"))
    unresolved: list[str] = []
    cited: set[str] = set()
    for folder in ("src", "tests"):
        for path in sorted((root / folder).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            bad, found = resolve(rows, text)
            unresolved += [f"{path.relative_to(root).as_posix()}: {token}" for token in bad]
            if folder == "tests" and path.suffix == ".py":
                cited |= found | cited_by_name(rows, text)
    return {
        "unresolved": unresolved,
        "uncited": sorted(i for i, status in rows.items() if status == "exists" and i not in cited),
        "planned_cited": sorted(i for i in cited if rows[i] == "planned"),
    }


# --- the real tree -----------------------------------------------------------------------


def test_catalogue_and_tests_agree() -> None:
    assert problems(REPO) == {"unresolved": [], "uncited": [], "planned_cited": []}


# --- the checks on synthetic catalogues and trees ----------------------------------------
# The areas ALPHA and BETA are not in the real catalogue, so these strings are no citation.

SAMPLE = """\
| ID | Behaviour | Verifies | Layer | Status |
|---|---|---|---|---|
| ALPHA-1 | first | FR-1 | unit | exists |
| ALPHA-2 | second | FR-1 | unit | planned |
| BETA-SUB-1 | third | FR-1 | unit | exists |
"""


def tree(tmp_path: Path, files: dict[str, str], catalogue: str = SAMPLE) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / CATALOGUE).write_text(catalogue, encoding="utf-8")
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_rows_and_status_come_from_the_id_column() -> None:
    assert parse_catalogue(SAMPLE) == {
        "ALPHA-1": "exists",
        "ALPHA-2": "planned",
        "BETA-SUB-1": "exists",
    }


@pytest.mark.parametrize(
    "text",
    [
        "",
        "| ID | Behaviour | Verifies | Layer | Status |\n|---|---|---|---|---|\n",
        SAMPLE + "| ALPHA-1 | again | FR-1 | unit | exists |\n",
        SAMPLE + "| ALPHA-3 | typo | FR-1 | unit | Exists |\n",
    ],
    ids=["empty", "header-only", "duplicate-id", "unknown-status"],
)
def test_catalogue_that_cannot_be_trusted_is_refused(text: str) -> None:
    with pytest.raises(ValueError, match=r"duplicate|no catalogue rows"):
        parse_catalogue(text)


@pytest.mark.parametrize("path", ["src/m.py", "tests/t.py", "tests/fixtures/f.ics"])
@pytest.mark.parametrize(
    "token", ["ALPHA-9", "ALPHA-1-Upper", "ALPHA-1x", "ALPHA-2..9", "ALPHA-2..1", "BETA-NEW-1"]
)
def test_token_that_matches_no_row_is_reported(tmp_path: Path, path: str, token: str) -> None:
    root = tree(tmp_path, {path: f"# {token}\n"})
    assert problems(root)["unresolved"] == [f"{path}: {token}"]


@pytest.mark.parametrize(
    "token", ["ALPHA-1", "ALPHA-1-off-grid", "ALPHA-1..2", "BETA-SUB-1", "SUB-1", "UTF-8"]
)
def test_token_that_matches_a_row_or_no_area_is_silent(tmp_path: Path, token: str) -> None:
    root = tree(tmp_path, {"src/m.py": f"# {token}\n"})
    (root / "tests/fixtures").mkdir(parents=True)
    (root / "tests/fixtures/blob.bin").write_bytes(b"\xff\xfe")  # not text: skipped, not an error
    assert problems(root)["unresolved"] == []


@pytest.mark.parametrize(
    ("files", "uncited"),
    [
        ({}, ["ALPHA-1", "BETA-SUB-1"]),
        ({"src/m.py": "# ALPHA-1 BETA-SUB-1\n"}, ["ALPHA-1", "BETA-SUB-1"]),
        ({"tests/fixtures/f.ics": "UID:ALPHA-1 BETA-SUB-1\n"}, ["ALPHA-1", "BETA-SUB-1"]),
        ({"tests/t.py": "def test_alpha_10_x(): ...\ndef test_beta_sub_1_x(): ...\n"}, ["ALPHA-1"]),
    ],
    ids=[
        "no-citation",
        "cited-in-source-only",
        "cited-in-fixture-only",
        "longer-number-is-another-id",
    ],
)
def test_exists_row_without_a_test_citation_is_reported(
    tmp_path: Path, files: dict[str, str], uncited: list[str]
) -> None:
    assert problems(tree(tmp_path, files))["uncited"] == uncited


@pytest.mark.parametrize(
    "text",
    [
        'ids=["ALPHA-1", "BETA-SUB-1-x"]',
        "# ALPHA-1..2 BETA-SUB-1",
        "def test_alpha_1_x(): ...\ndef test_beta_sub_1(): ...",
    ],
    ids=["parametrize-ids", "range", "test-name"],
)
def test_exists_row_cited_by_a_test_is_silent(tmp_path: Path, text: str) -> None:
    assert problems(tree(tmp_path, {"tests/t.py": text}))["uncited"] == []


@pytest.mark.parametrize("text", ["# ALPHA-2", "# ALPHA-1..2", "def test_alpha_2_x(): ..."])
def test_planned_row_cited_by_a_test_is_reported(tmp_path: Path, text: str) -> None:
    assert problems(tree(tmp_path, {"tests/t.py": text}))["planned_cited"] == ["ALPHA-2"]


@pytest.mark.parametrize(
    "files",
    [{}, {"src/m.py": "# ALPHA-2\n"}, {"tests/fixtures/f.ics": "UID:ALPHA-2\n"}],
    ids=["no-citation", "cited-in-source-only", "cited-in-fixture-only"],
)
def test_planned_row_not_cited_by_a_test_is_silent(tmp_path: Path, files: dict[str, str]) -> None:
    assert problems(tree(tmp_path, files))["planned_cited"] == []
