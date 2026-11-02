# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Judge feature files against the rubrics of D-18 (`tests/meta/judges.md`).

    uv run --script scripts/judge_features.py [FILE ...]
    uv run --script scripts/judge_features.py --calibrate tests/meta/judge-set

Without FILE it judges the feature files under tests/features/ that differ from the merge
base with origin/main (else main), untracked ones included. Each file costs one
`claude --print` call on the operator's own Claude Code login, so no API key is needed.
While the judges are advisory, the finding lines go into the pull request body
(CONTRIBUTING.md § Pull requests). Stdlib only, like every script here.

The call is isolated: it runs in an empty folder and loads no settings, hooks, plugins, MCP
servers, skills, memory or tools of the caller (`--setting-sources ""`), and its system
prompt replaces Claude Code's. The judge sees only the rubric and the file, so a hook that
works on the operator's sessions cannot change what the calibration measured.

--calibrate measures S1 of D-18 for each judge over a labelled set: `<judge>--defect-NN.feature`
holds one seeded defect of that judge, `clean-NN.feature` none for any judge. A judge passes
when it flags at least 26 of every 30 defect files and at most 3 of every 30 clean files, on at
least 30 of each.

No fallback model: an answer from another model would not be the model the calibration
measured. A change of MODEL or of the rubric reruns it.

A section of the rubric says `Status: advisory` or `Status: blocking`; a judge turns blocking
once it passes the calibration. `--blocking` (the push stage) fails only on a finding of a
blocking judge, and with no blocking judge it passes at once, without the CLI or a call.

Exit codes: 0 judged (advisory findings are advice) or every judge passed; 1 a blocking judge
found something, or a judge failed the calibration; 2 a usage, rubric, git or claude error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, override

MODEL = "claude-opus-5-5"
CLAUDE = (  # one isolated judge call; --tools takes a list, so the prompt goes to stdin
    "claude", "--print", "--model", MODEL, "--effort", "medium", "--output-format", "json",
    "--setting-sources", "", "--settings", '{"disableAllHooks": true}', "--strict-mcp-config",
    "--disable-slash-commands", "--no-session-persistence", "--tools", "",
)  # fmt: skip
TIMEOUT = 600
ROOT = Path(__file__).resolve().parents[1]
RUBRIC = Path("tests/meta/judges.md")
FEATURES = Path("tests/features")
SECTION = re.compile(r"^## (judge-[a-z]+)\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
SEED = re.compile(r"(?:(judge-[a-z]+)--defect|clean)-\d+\.feature")
STATUS = re.compile(r"^Status: (advisory|blocking)$", re.MULTILINE)
SEEDS, FOUND, FALSE = 30, 26, 3  # S1: per 30 seeds, at least 26 found and at most 3 false
INSTRUCTION = """\
You review one Gherkin feature file against the rubrics below. Report a finding only where a
rubric's Flag list clearly applies; when in doubt, report nothing. A finding names the judge,
the line number printed before `|`, and one sentence why. A file with no defect gets an empty
list."""

type Post = Callable[[dict[str, Any]], dict[str, Any]]


class JudgeError(Exception):
    """A rubric, git or claude failure: the run cannot judge, so it must not pass."""


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    judge: str
    reason: str

    @override
    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.judge}: {self.reason}"


def rubrics(text: str) -> dict[str, str]:
    """Each `## judge-<name>` section of the rubric file, by judge."""
    found = {match[1]: match[2].strip() for match in SECTION.finditer(text)}
    if not found:
        msg = "the rubric holds no `## judge-<name>` section"
        raise JudgeError(msg)
    return found


def blocking(rubric: Mapping[str, str]) -> set[str]:
    """The judges whose section says `Status: blocking`; each section must state a status."""
    found: set[str] = set()
    for name, text in rubric.items():
        if not (match := STATUS.search(text)):
            msg = f"{name} has no `Status: advisory` or `Status: blocking` line"
            raise JudgeError(msg)
        if match[1] == "blocking":
            found.add(name)
    return found


def sender() -> Post:
    """The real call through the claude CLI; no CLI, no run."""
    if not shutil.which("claude"):
        msg = "the claude CLI is not on PATH: the judges run through it (CI never runs them)"
        raise JudgeError(msg)
    return ask


def request(feature: str, rubric: Mapping[str, str]) -> dict[str, Any]:
    """The system prompt, schema and numbered file that judge one feature file."""
    numbered = "\n".join(f"{n:>4}| {line}" for n, line in enumerate(feature.splitlines(), 1))
    sections = "\n\n".join(
        f"## {name}\n{STATUS.sub('', text).strip()}" for name, text in rubric.items()
    )
    finding = {
        "type": "object",
        "properties": {
            "judge": {"type": "string", "enum": list(rubric)},
            "line": {"type": "integer"},
            "reason": {"type": "string"},
        },
        "required": ["judge", "line", "reason"],
        "additionalProperties": False,
    }
    schema = {
        "type": "object",
        "properties": {"findings": {"type": "array", "items": finding}},
        "required": ["findings"],
        "additionalProperties": False,
    }
    return {"system": f"{INSTRUCTION}\n\n{sections}", "schema": schema, "prompt": numbered}


def ask(
    body: Mapping[str, Any], run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
) -> dict[str, Any]:
    """One isolated claude call in an empty folder; output that is no JSON fails the run."""
    args = [*CLAUDE, "--system-prompt", body["system"], "--json-schema", json.dumps(body["schema"])]
    env = {name: value for name, value in os.environ.items() if name != "CLAUDECODE"}
    try:
        with tempfile.TemporaryDirectory() as empty:
            done = run(
                args,
                input=body["prompt"],
                capture_output=True,
                text=True,
                cwd=empty,
                env=env,
                timeout=TIMEOUT,
                check=False,
            )
    except subprocess.TimeoutExpired:
        msg = f"claude did not answer within {TIMEOUT} s"
        raise JudgeError(msg) from None
    try:
        answer: dict[str, Any] = json.loads(done.stdout)
    except json.JSONDecodeError:
        msg = f"claude exited {done.returncode}: {(done.stderr or done.stdout).strip()[:500]}"
        raise JudgeError(msg) from None
    return answer


def findings(file: str, answer: Mapping[str, Any], judges: Sequence[str]) -> list[Finding]:
    """The findings of one answer; an error answer means no verdict."""
    if answer.get("is_error") or answer.get("subtype") != "success":
        detail = str(answer.get("result", ""))[:300]
        msg = f"{file}: claude answered {answer.get('subtype')!r}, no verdict: {detail}"
        raise JudgeError(msg)
    try:
        listed = answer["structured_output"]["findings"]
    except (KeyError, TypeError) as error:
        msg = f"{file}: the answer is no findings list ({error})"
        raise JudgeError(msg) from None
    return [
        Finding(file, int(item["line"]), item["judge"], item["reason"])
        for item in listed
        if item["judge"] in judges
    ]


def judge(paths: Sequence[Path], rubric: Mapping[str, str], send: Post) -> list[Finding]:
    found: list[Finding] = []
    for path in paths:
        answer = send(request(path.read_text(encoding="utf-8"), rubric))
        found += findings(path.as_posix(), answer, list(rubric))
    return found


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )


def changed(root: Path) -> list[Path]:
    """Feature files that differ from the merge base with main, untracked ones included."""
    for ref in ("origin/main", "main"):
        if (fork := git(root, "merge-base", "HEAD", ref)).returncode == 0:
            break
    else:
        msg = "neither origin/main nor main to compare with: name the files"
        raise JudgeError(msg)
    scope = ("--", FEATURES.as_posix())
    diffed = git(root, "diff", "--name-only", "--diff-filter=d", fork.stdout.strip(), *scope)
    untracked = git(root, "ls-files", "--others", "--exclude-standard", *scope)
    names = {*diffed.stdout.splitlines(), *untracked.stdout.splitlines()}
    return [root / name for name in sorted(names) if name.endswith(".feature")]


def calibrate(folder: Path, rubric: Mapping[str, str], send: Post) -> tuple[list[str], bool]:
    """S1 per judge: the lines to print and whether every judge passed."""
    labels: dict[Path, str | None] = {}
    for path in sorted(folder.glob("*.feature")):
        if not (match := SEED.fullmatch(path.name)) or (match[1] and match[1] not in rubric):
            msg = f"{path}: not <judge>--defect-NN.feature or clean-NN.feature of a known judge"
            raise JudgeError(msg)
        labels[path] = match[1]
    flagged = {path: {f.judge for f in judge([path], rubric, send)} for path in labels}
    clean = [path for path, label in labels.items() if label is None]
    lines, passed = [], True
    for name in rubric:
        defects = [path for path, label in labels.items() if label == name]
        found = sum(name in flagged[path] for path in defects)
        false = sum(name in flagged[path] for path in clean)
        ok = min(len(defects), len(clean)) >= SEEDS
        ok = ok and found * SEEDS >= FOUND * len(defects) and false * SEEDS <= FALSE * len(clean)
        passed = passed and ok
        verdict = (
            "pass" if ok else f"FAIL (needs {FOUND}/{SEEDS} found, at most {FALSE}/{SEEDS} false)"
        )
        lines.append(
            f"{name}: {found}/{len(defects)} defects found, {false}/{len(clean)} clean files flagged: {verdict}"
        )
    return lines, passed


def main(
    argv: Sequence[str] | None = None,
    send: Post | None = None,
    rubric_file: Path = ROOT / RUBRIC,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("files", nargs="*", type=Path, help="feature files (default: changed ones)")
    parser.add_argument(
        "--calibrate", type=Path, metavar="DIR", help="measure S1 over a labelled set"
    )
    parser.add_argument(
        "--blocking", action="store_true", help="fail on a finding of a blocking judge (push stage)"
    )
    args = parser.parse_args(argv)
    try:
        rubric = rubrics(rubric_file.read_text(encoding="utf-8"))
        gate = blocking(rubric)
        if args.calibrate is not None:
            lines, passed = calibrate(args.calibrate, rubric, send or sender())
            print("\n".join(lines))
            return 0 if passed else 1
        if args.blocking and not gate:
            return 0  # no judge has passed its calibration yet: nothing blocks, no call needed
        paths = args.files or changed(ROOT)
        found = judge(paths, rubric, send or sender()) if paths else []
    except JudgeError as error:
        print(f"judge_features: {error}", file=sys.stderr)
        return 2
    for finding in found:
        print(finding)
    return 1 if args.blocking and any(finding.judge in gate for finding in found) else 0


if __name__ == "__main__":
    sys.exit(main())
