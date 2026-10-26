# Security policy

Milchglas exists to keep private calendar content private, so a leak of that content
counts as a security vulnerability, not just a bug.

## Supported versions

The project is pre-1.0. Only the latest release (and `main`) receives security fixes.

## Reporting a vulnerability

**Do not open a public issue, discussion or pull request for a vulnerability.**

Report it privately through GitHub's
[private vulnerability reporting](https://github.com/Prism-Purpose-Pace/milchglas/security/advisories/new).
Please include:

- affected version or commit,
- a description and the impact you expect,
- steps or a minimal proof of concept to reproduce it,
- whether you want to be credited, and under which name.

Never attach real calendar data, feed URLs with live tokens, or credentials. Use
synthetic events and placeholder tokens instead.

If the private reporting form is not available to you, open a public issue that only
asks for a private channel and says nothing about the problem.

## Reports we can act on

Include steps that reproduce the problem with synthetic events and placeholder tokens. A
report written with AI assistance is welcome when you have verified the issue yourself and
say so. Output of an automated scanner without a demonstrated impact is closed without a CVE.

## What to expect

This is a volunteer, single-maintainer project; the targets below are best effort:

- acknowledgement within 7 days,
- an initial assessment within 14 days,
- a fix or mitigation, a GitHub Security Advisory and (if applicable) a CVE, released
  in coordination with you. The default disclosure deadline is 90 days after the report.

## Severity

We rate a confirmed report with the CVSS calculator of GitHub's advisory form, then apply the
impact scale of the [threat model](docs/threat-model.md) as a floor. High at least: private
event content or the CalDAV credential is disclosed, or the feed that consumers receive is
wrong or empty. Medium at least: the feed token or the busy pattern reaches a third party.

## In scope

- Private event content (titles, descriptions, locations, attendees) reaching the feed,
  logs, error messages, state files or HTTP responses.
- Feed token disclosure or bypass: token in logs, timing side channels, responses that
  distinguish a wrong token from an unknown path.
- Anything that lets an outside party read, alter or delete source calendars (Milchglas
  must only ever read them).
- A source outage or malformed input that replaces the last good feed with an empty or
  wrong one.
- Vulnerable dependencies that are reachable from Milchglas' code paths.
- Weaknesses in this repository's CI or release pipeline that let an outsider change a
  release asset or read a repository secret.

## Out of scope

- How consumers (calendar clients, booking tools) cache or display a feed they
  subscribed to.
- Compromise of the CalDAV server or of the host Milchglas runs on.
- Findings that require a leaked `CALDAV_SECRET` or a leaked feed token as a
  precondition, unless Milchglas itself leaked it.

## Hardening in this repository

Secret scanning with push protection, Dependabot alerts and security updates, CodeQL,
OpenSSF Scorecard, SHA-pinned GitHub Actions with least-privilege tokens, and local
pre-commit gates (gitleaks, trufflehog, osv-scanner). See [TOOLING.md](TOOLING.md).

Release assets carry build provenance signed through Sigstore. Verify a downloaded file
with `gh attestation verify <file> --repo Prism-Purpose-Pace/milchglas`.
