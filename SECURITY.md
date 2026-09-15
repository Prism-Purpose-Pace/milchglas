# Security policy

Milchglas exists to keep private calendar content private, so a leak of that content
counts as a security vulnerability, not just a bug.

## Supported versions

The project is pre-1.0. Only the latest release (and `main`) receives security fixes.

## Reporting a vulnerability

**Do not open a public issue, discussion or pull request for a vulnerability.**

Report it privately through GitHub's
[private vulnerability reporting](https://github.com/philippsied/milchglas/security/advisories/new).
Please include:

- affected version or commit,
- a description and the impact you expect,
- steps or a minimal proof of concept to reproduce it,
- whether you want to be credited, and under which name.

Never attach real calendar data, feed URLs with live tokens, or credentials. Use
synthetic events and placeholder tokens instead.

## What to expect

This is a volunteer, single-maintainer project; the targets below are best effort:

- acknowledgement within 7 days,
- an initial assessment within 14 days,
- a fix or mitigation, a GitHub Security Advisory and (if applicable) a CVE, released
  in coordination with you. The default disclosure deadline is 90 days after the report.

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
