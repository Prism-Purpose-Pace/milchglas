# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Audit PEP 723 inline dependencies across the repo for known CVEs via `uv audit` (OSV).

Most scripts here are stdlib-only (`dependencies = []`) so this is usually a no-op; it
fires the moment a script declares a 3rd-party dependency.

Modes:
  --mode warn   report findings, always exit 0   (pre-commit: inform, do not block)
  --mode block  exit 1 if any vulnerability found (pre-push: hard gate)

Transient failures (uv missing, network down, timeout, host-denied OSV resolve) degrade to a
notice + exit 0 in BOTH modes — a sandbox/outage must not self-block every push. But a
parse/resolve error of the input, or an exit 0 without a positive "no known vulnerabilities"
assertion, is fail-closed: it blocks in --mode block (A3). CI is the non-bypassable backstop.

Usage: uv run --script scripts/audit_script_deps.py --mode block [PATHS...]
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOTS = ["scripts"]
PEP723 = re.compile(r"^# /// script\s*$.*?^# ///\s*$", re.M | re.S)
DEPS = re.compile(r"dependencies\s*=\s*\[(.*?)\]", re.S)
FOUND = re.compile(r"Found (\d+) known vulnerabilit")
PKG = re.compile(r"has \d+ known vulnerabilit")
NO_VULN = re.compile(r"no known vulnerabilit", re.I)
# Transient/offline infra: degrade to WARN, never block (the sandbox denies the OSV host,
# so a network outage must not self-block every push). Genuine parse/resolve errors of the
# input fall through to "error" and fail-closed in block mode.
TRANSIENT = re.compile(
    r"network|timed? ?out|failed to (fetch|download|connect)|connection|"
    r"could not (connect|resolve)|offline|temporar|\bdns\b|sending request|"
    r"\btls\b|\bssl\b|certificate|50[23]\b|\b429\b|unreachable|no route",
    re.I,
)


def declares_deps(text: str) -> bool:
    block = PEP723.search(text)
    if not block:
        return False
    deps = DEPS.search(block.group(0))
    if not deps:
        return False
    # strip comment markers / whitespace / commas; non-empty remainder == real deps
    return bool(re.sub(r"[#\s,]", "", deps.group(1)))


def find_scripts(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        base = Path(p)
        if not base.exists():
            continue
        for f in sorted(base.rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            try:
                if declares_deps(f.read_text(encoding="utf-8")):
                    out.append(f)
            except OSError:
                continue
    return out


def classify(returncode: int, blob: str) -> tuple[str, str]:
    """Pure classifier. status in {clean, vuln, transient, error}.

    - clean: exit 0 AND a positive "no known vulnerabilities" assertion — a bare exit 0
      is not proof the scan ran clean (A3: assert the positive before declaring clean).
    - vuln: a reported "Found N known vulnerabilities" with N > 0.
    - transient: offline / network / host-denied resolve — degrade to WARN, never block.
    - error: a parse/resolve error, or exit 0 without the positive marker — fail-closed
      in block mode.
    """
    if returncode == 0:
        if NO_VULN.search(blob):
            return "clean", ""
        return "error", "audit exited 0 without a 'no known vulnerabilities' assertion"
    m = FOUND.search(blob)
    if m and int(m.group(1)) > 0:
        return "vuln", blob
    tail = blob.strip().splitlines()[-1] if blob.strip() else "audit error"
    if TRANSIENT.search(blob):
        return "transient", tail
    return "error", tail


def audit(f: Path) -> tuple[str, str]:
    """Run `uv audit` for one script and classify the result."""
    try:
        r = subprocess.run(
            ["uv", "audit", "--script", str(f), "--preview-features", "audit-command"],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError:
        return "transient", "uv not found"
    except subprocess.TimeoutExpired:
        return "transient", "audit timed out"
    return classify(r.returncode, r.stdout + r.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["warn", "block"], default="warn")
    ap.add_argument("paths", nargs="*")
    args = ap.parse_args()

    scripts = find_scripts(args.paths or ROOTS)
    if not scripts:
        print("cve-audit: no PEP 723 scripts with declared dependencies — nothing to audit.")
        return 0

    vulnerable: list[tuple[Path, str]] = []
    errored: list[tuple[Path, str]] = []
    skipped: list[tuple[Path, str]] = []
    for f in scripts:
        status, detail = audit(f)
        if status == "vuln":
            vulnerable.append((f, detail))
        elif status == "error":
            errored.append((f, detail))
        elif status == "transient":
            skipped.append((f, detail))

    for f, detail in vulnerable:
        print(f"cve-audit: VULNERABLE  {f}")
        for line in detail.splitlines():
            s = line.strip()
            if PKG.search(s) or FOUND.search(s):
                print(f"    {s}")
    for f, detail in errored:
        print(f"cve-audit: ERROR       {f}  ({detail})")
    for f, reason in skipped:
        print(f"cve-audit: SKIPPED     {f}  ({reason}) — transient, not blocking")

    blocking = vulnerable + errored
    if blocking and args.mode == "block":
        print(
            f"\ncve-audit: push BLOCKED (fail-closed) — {len(vulnerable)} script(s) with "
            f"known CVEs, {len(errored)} audit error(s). Pin safe versions / fix the audit input."
        )
        return 1
    if blocking:
        print(
            f"\ncve-audit: WARNING — {len(vulnerable)} CVE finding(s), {len(errored)} audit "
            f"error(s) (commit allowed; push will block)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
