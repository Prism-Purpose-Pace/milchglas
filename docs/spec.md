# Milchglas — Product Requirements (v0.3)

> v0.3 is the public edition of the internal v0.2 draft: product renamed, operator-specific details removed.

**Status:** Draft · **Date:** 2026-09-15 · **Supersedes:** Architecture & Implementation Concept v0.1 (2026-09-13), now folded into Sections 7, 9 and 12 of this PRD.

> **For contributors and AI agents:** Section 0 explains the markers used. Build the MVP scope (Section 6, "MVP" column) first. Everything in Section 12 is backlog and must not be pulled forward without an explicit maintainer decision. Deployment options are in Section 9; the default target is Option B unless the maintainer decides otherwise (Decision D-9).

---

## 0. Conventions

| Marker | Meaning |
|---|---|
| **[FACT]** | Confirmed from vendor documentation or repeated, consistent community reports; source in Section 14 |
| **[REPORT]** | Single community report or bug tracker entry; plausible, not vendor-confirmed |
| **[VERIFY V-n]** | Assumption with a concrete test in Section 11; do not build irreversibly on it before the test |
| **[DECIDED D-n]** | Decision recorded in Section 5; do not re-decide silently |
| **[OPEN Q-n]** | Product decision not yet made (Section 13); implement the stated default, keep it configurable |
| **[MVP]** / **[LATER]** | In scope for the first working version / backlog |

Document language is English (the project's default for specs). Runbook and consumer-setup docs may be German ([OPEN Q-7]).

---

## 1. Background

The operator's calendar landscape:

| System | Role | Notes |
|---|---|---|
| **mailbox.org** (Open-Xchange App Suite) | Business calendars, business mail | Calendar/address book stored unencrypted at the provider [FACT] |
| **Nextcloud** (managed hosting) | Private calendars | Version and patch cadence controlled by the hosting provider |
| **meetergo** | Self-service booking; writes bookings into the mailbox.org calendar via CalDAV | German processor; AVV (data processing agreement) required regardless of this project |
| **Self-hosted PaaS** (e.g. Coolify, on a VPS) | General self-hosting platform | Candidate host for this service |
| **Shared web hosting** | Websites | Candidate host for this service |

**Problem:** Two questions must be answerable without moving private appointment content out of Nextcloud:

1. **Visual** — in mailbox.org, "am I privately booked on day X between Y and Z?" as a second, subscribed calendar of anonymous blocks.
2. **Automated** — meetergo must not offer slots that collide with private appointments.

**Core insight from the research (Section 4):** none of the three systems can produce a *busy-only* view of a foreign calendar. Nextcloud shares are access control, not redaction; mailbox.org can subscribe to an ICS feed but not compute free/busy from another server; meetergo can read a feed but connecting Nextcloud directly would expose full content. Therefore a small self-operated service ("Milchglas") reads Nextcloud, reduces everything to time intervals, and publishes an anonymous ICS feed that both consumers subscribe to.

---

## 2. Goals

| ID | Goal | Priority |
|---|---|---|
| G1 | Publish an ICS feed that contains only busy intervals — no titles, descriptions, locations, attendees, categories, alarms | Must |
| G2 | Feed is consumable by mailbox.org (OX iCal subscription) and by meetergo (read-only ICS calendar) | Must |
| G3 | Private event content never leaves Nextcloud; if it must transit Milchglas it is held in memory only, never persisted or logged | Must |
| G4 | Wrong intervals are prevented by design: recurrences, exceptions, DST and all-day events are handled correctly | Must |
| G5 | Fail-safe: a source outage never silently turns into "free" slots | Must |
| G6 | Operable by one person in the evening without on-call: boring technology, one config file, one log | Must |
| G7 | Maintenance without touching secrets: swap/enable/disable source calendars, rotate the feed URL, force a refresh | Should (MVP via config file; UI later) |
| G8 | Host-portable: the same core code runs under Options A, B and C (Section 9) | Should |
| G9 | Data minimisation of the busy pattern itself: short window, rounding, merging | Should |

## 3. Non-goals

- Two-way sync or writing into any calendar (bookings continue to flow meetergo → mailbox.org).
- Replacing meetergo, Nextcloud Appointments or OX scheduling.
- Multi-tenant or multi-user operation.
- Mobile push; phones may subscribe to the same feed (Section 12).
- Encrypting the feed for consumers (meetergo requires public URLs [FACT]; OX credential support for feeds is unverified).
- Protecting against the providers themselves (the Nextcloud host, the PaaS/hosting provider, mailbox.org, meetergo) seeing what they legitimately process.

---

## 4. Research findings (as of 2026-09-13)

### 4.1 Nextcloud
- Calendars can be published via a public read-only link; `?export` yields ICS **with full details** [FACT].
- No calendar-level "share/export busy only" exists; feature requests open since 2016 (calendar #171, #1044) [FACT].
- Per-event visibility exists: *Show full event* (`CLASS:PUBLIC`, default) / *When shared show only busy* (`CLASS:CONFIDENTIAL`) / *Hide* (`CLASS:PRIVATE`). There is no per-calendar default; every event must be set manually (#4086) [FACT].
- Enforcement is unreliable: "urgent privacy issue" report that all group sharees see full data despite the option (calendar #7694, Nov 2025, Calendar 5.5.9 / dav 1.31.1) [REPORT]; CalDAV clients historically received full titles while the web UI showed "busy" (server #10392) [REPORT]; sharees with edit rights see everything, and editing a confidential event overwrites the owner's title with "Busy" (#10865, #4044) [REPORT]; attendees always see full details (#7846) [REPORT].
- Free/busy lookups work only inside the same instance; no external free/busy export [FACT].
- Nextcloud can *subscribe* to external WebCal/ICS feeds (reverse direction is free) [FACT].
- Nextcloud Appointments conflict detection silently ignores subscribed ICS feeds (server #60312) [REPORT] — relevant only if meetergo were ever replaced.
- **Design consequence [DECIDED D-3]:** Nextcloud sharing is used for *least privilege* (read-only service user), never for redaction. Redaction happens in Milchglas. `CLASS:PRIVATE` must never be used on private events — hidden events would become bookable slots.

### 4.2 mailbox.org / Open-Xchange
- External iCal feeds **can** be subscribed in the web client: arrow next to *Neuer Termin* → *Von URL (iCal) importieren* → dialog *iCal-Feed abonnieren* → calendar appears under *Meine Kalender* [FACT, mailbox.org KB migration article]. An older KB FAQ states the opposite; the newer article wins, to be confirmed by test [VERIFY V-1].
- OX's ICal calendar provider caches feeds server-side; the refresh interval is admin-configured and a feed's `REFRESH-INTERVAL` is honoured [FACT, OX middleware docs]. The effective interval at mailbox.org is unknown [VERIFY V-1].
- Whether optional HTTP credentials can be entered for a feed at mailbox.org is unknown (OX supports it in principle) [VERIFY V-1].
- Public share links (`?ical=true`) are read-only; anyone with the link sees all content [FACT].
- Subscribed feed calendars may not sync to phones through mailbox.org's CalDAV [REPORT, user forum].
- Calendars are not encrypted at rest [FACT] — an argument for never storing private titles there.

### 4.3 meetergo
- Connects Nextcloud via CalDAV, mailbox.org via generic CalDAV, and any ICS/iCal link read-only for availability checks; bookings are not written to ICS calendars [FACT, help.meetergo.com, updated 2026-01].
- ICS URLs must be publicly reachable; services requiring authentication are not supported [FACT].
- Multiple connected calendars are all checked for conflicts; per-calendar "read appointments" toggles exist [FACT].
- Refresh cadence described as "regelmäßig" (minutes) [FACT, unspecific].

### 4.4 Shared web hosting (Passenger-based)
- Python runs **only** as WSGI apps under Phusion Passenger; no CLI, no SSH Python, no Python cron [FACT, hosting provider Helpcenter].
- Python/Node/Ruby are available only from a higher hosting tier upward [FACT].
- `pip` is not available; packages must be uploaded [FACT/REPORT].
- SSH access and (shell/PHP) cron jobs are included in all tariffs [FACT].
- Changed Python settings only apply after *disable → enable*; the control-panel session expires silently after ~15 min [REPORT].
- Panel generation differs by package age; the operator's specific package must be checked [VERIFY V-6].

### 4.5 Prior art (not adopted, informs design)
- `ical-filter-proxy` (fork with `freebusy_mode`): strips everything except date/time/status from an ICS feed. Requires an existing full-detail ICS URL as input.
- `keeper.sh`: multi-source calendar sync with per-source privacy stripping; needs Postgres + Redis — too heavy for this VPS.
- `zeitfenster`: schedule tool, not a feed redactor.

### 4.6 CalDAV protocol capabilities (design leverage)
- `calendar-query` REPORT with `<C:expand>` makes the server expand recurrences and apply exceptions [FACT, RFC 4791; sabre/dav implements it] [VERIFY V-4].
- `free-busy-query` REPORT returns a server-computed `VFREEBUSY` — content never transits the client [FACT, RFC 4791]. Nextcloud (sabre/dav-based) is expected to support it [VERIFY V-3]. [LATER]

---

## 5. Decision log

| ID | Decision | Status | Rationale |
|---|---|---|---|
| D-1 | Build a self-operated busy-only feed ("Milchglas") instead of any built-in path | Decided 2026-09-13 | No built-in busy-only export exists (4.1–4.3) |
| D-2 | Nextcloud access via a dedicated service user `svc-milchglas` with read-only shares, zero quota, revocable app password | Decided | Least privilege; a compromise yields read access to busy times, never write access or files |
| D-3 | Redaction happens exclusively in Milchglas; never rely on Nextcloud `CLASS`; never use `CLASS:PRIVATE` on private events | Decided | Enforcement bugs (4.1); hidden events create false-free slots |
| D-4 | Both consumers (mailbox.org, meetergo) subscribe to the Milchglas feed; Nextcloud is **not** connected to meetergo directly | Decided | Data minimisation toward the third-party processor |
| D-5 | MVP first (≈60 lines core logic + cron + static file behind HTTPS); v0.1 concept features become backlog | Decided 2026-09-13 | The maintainer's challenge was correct: most of v0.1 is optional; four items are not (D-7) |
| D-6 | Window: today → +28 days (operator's proposal) — conditional on meetergo's booking horizon ≤ 28 days | Proposed; confirm [OPEN Q-2] | Shorter window = less pattern exposure |
| D-7 | Mandatory even in MVP: (a) correct recurrence expansion, (b) merged intervals (set union), (c) deterministic UIDs, (d) never overwrite the last good feed on failure | Decided | Correctness and safety, not architecture |
| D-8 | Output as `VEVENT`s in UTC, all-day as `DATE`, `SUMMARY` "Blocker Privat" (configurable), `TRANSP:OPAQUE` | Proposed | OX and meetergo consume VEVENTs; UTC avoids VTIMEZONE; stable UIDs prevent OX churn |
| D-9 | Deployment target | **Open — see Section 9**; recommendation: Option B now | |
| D-10 | Documentation language English; runbook may be German | Proposed [OPEN Q-7] | Maintainer defaults |
| D-11 | Secrets only via environment (or `0600` file); never entered or shown in any UI | Proposed | Avoids crypto dependency; standard on self-hosted PaaS platforms |

---

## 6. Functional requirements

| ID | Requirement | MVP | Later |
|---|---|---|---|
| FR-1 | Read all *enabled* calendars of the service user via CalDAV (Basic auth, HTTPS, 10 s timeout, 3 retries with backoff) | ✔ | |
| FR-2 | Expand recurrences server-side (`expand`); local expansion with `recurring-ical-events` as fallback | ✔ | |
| FR-3 | Exclude `STATUS:CANCELLED`, `TRANSP:TRANSPARENT`, and events the owner has declined (`PARTSTAT=DECLINED` for configured owner e-mails) | ✔ | |
| FR-4 | Reduce every event to `(start, end, tentative, allday)` immediately; discard all other fields | ✔ | |
| FR-5 | Window clip: `[today 00:00 local, today + window_days]` | ✔ | |
| FR-6 | Round to grid (default 15 min; start floored, end ceiled, computed in `Europe/Berlin`) and merge overlapping/adjacent intervals | ✔ | |
| FR-7 | Emit RFC 5545 ICS: `VEVENT` per merged interval, UTC, deterministic `UID`, `REFRESH-INTERVAL`/`X-PUBLISHED-TTL` = TTL, `X-WR-CALNAME` | ✔ | |
| FR-8 | Write the feed atomically; on any failure keep the previous file and record the error | ✔ | |
| FR-9 | Serve the feed at `https://<host>/f/<token>.ics` over HTTPS; unknown paths → identical 404 | ✔ | |
| FR-10 | Refresh every 15 min (cron/timer/loop) — mechanism depends on Option (Section 9) | ✔ | |
| FR-11 | `/healthz`: 200 if last success < 60 min, else 503; no other data | ✔ | |
| FR-12 | Config file lists calendars with `enabled` flags; a "swap" is share/unshare in Nextcloud + flag edit | ✔ | |
| FR-13 | All-day handling mode: `busy` (default) / `ignore` / `working_hours` [OPEN Q-1] | ✔ (busy only) | modes |
| FR-14 | Tentative handling: `busy` (default) / `separate` / `ignore` | ✔ (busy only) | modes |
| FR-15 | Fail-closed after `stale_max_age` (default 48 h): emit all-day blocker events "Milchglas: Quelle nicht erreichbar" | | ✔ |
| FR-16 | One token per consumer (`mailbox`, `meetergo`, `mobile`) with rotation and grace period | | ✔ |
| FR-17 | Calendar discovery via PROPFIND and enable/disable toggles in an admin UI | | ✔ |
| FR-18 | Admin UI: dashboard (counts/timestamps only), refresh now, rotate token, settings | | ✔ |
| FR-19 | Primary acquisition via `free-busy-query` so content never transits Milchglas | | ✔ [VERIFY V-3] |
| FR-20 | CalDAV *push* variant: write blocker VEVENTs into a dedicated mailbox.org calendar (fallback if feed subscription fails V-1) | | ✔ |

---

## 7. Non-functional requirements

### 7.1 Privacy
- NFR-P1 No Class-A content (titles, descriptions, attendees, locations) is ever written to disk, logs, metrics or error messages. Tests assert absence.
- NFR-P2 The busy pattern is minimised: window ≤ 28 days by default, 15-min grid, merged blocks (block count ≠ appointment count).
- NFR-P3 Feed output contains exactly: `UID, DTSTAMP, DTSTART, DTEND, SUMMARY, TRANSP, STATUS` (+ optional `X-MICROSOFT-CDO-BUSYSTATUS`).

### 7.2 Security
- NFR-S1 Feed access by capability URL: ≥ 256-bit random token, constant-time comparison, HTTPS only, `X-Robots-Tag: noindex`, `Referrer-Policy: no-referrer`, no directory listing.
- NFR-S2 Secrets (`CALDAV_SECRET`, session secret) from environment or a `0600` file outside any document root; never in Git, images, config JSON or UI.
- NFR-S3 Nextcloud service user has read-only shares only, zero quota; app password revocable in one click.
- NFR-S4 Process runs unprivileged; where possible read-only filesystem except the state directory; outbound connections only to the Nextcloud host.
- NFR-S5 Logs redact tokens; access logs must not contain the feed path with token (strip or hash at the proxy).
- NFR-S6 [LATER, with admin UI] scrypt password hashing, lockout after 5 failures, HMAC-signed `HttpOnly; Secure; SameSite=Strict` cookie, CSRF double-submit, optional CIDR allow-list.

### 7.3 Reliability / fail-safety
- NFR-R1 Source failure never produces an empty or missing feed (D-7d).
- NFR-R2 `/healthz` enables external alerting (uptime monitor → e-mail).
- NFR-R3 [LATER] Fail-closed blockers after 48 h (FR-15).

### 7.4 Correctness
- NFR-C1 Golden tests: overlap merge, adjacency, grid rounding, DST spring/fall in `Europe/Berlin`, all-day, multi-day, tentative, cancelled, declined, RRULE + EXDATE + overridden instance, window clipping, UID determinism, RFC 5545 folding; output re-parses with `icalendar`.
- NFR-C2 Contract tests against a sabre/dav-based server (Baïkal container) for PROPFIND, `calendar-query` + `expand`, and (later) `free-busy-query`.

### 7.5 Operability
- NFR-O1 One config file, one state file, one log stream; `python -m milchglas refresh` is idempotent and safe to run by hand.
- NFR-O2 Runbook covers: rotate token, swap calendar, recover from stale/fail-closed, migrate host (copy state dir).
- NFR-O3 Runtime dependencies pure Python only (`icalendar`, `python-dateutil`, `tzdata`, `recurring-ical-events`, `x-wr-timezone`) so Options A–C share one codebase.

---

## 8. Solution concept (host-independent core)

```
Nextcloud ──read-only CalDAV (svc-milchglas)──► Milchglas core
                                                   fetch → expand → filter → reduce → round → merge → emit
                                                   └─► busy.ics (atomic write; keep last good on error)
                                                              │
                                        HTTPS  /f/<token>.ics │  (static file or WSGI route)
                                   ┌──────────────────────────┴──────────────────────────┐
                                   ▼                                                     ▼
                     mailbox.org: subscribed iCal feed                     meetergo: ICS conflict calendar
                     "Blocker Privat" blocks                               (bookings still written to mailbox.org via CalDAV)
```

**Core pipeline (pure functions, unit-tested):**
```
intervals = fetch_all(enabled_calendars, window)            # FR-1..FR-4
intervals = clip(intervals, window)                          # FR-5
intervals = round_to_grid(intervals, 15min, tz=Europe/Berlin)
intervals = merge(sorted(intervals))                         # FR-6  (set union)
ics       = emit(intervals, summary="Blocker Privat")        # FR-7
atomic_replace("busy.ics", ics) if ok else keep_previous()   # FR-8
```

**ICS skeleton:**
```
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Milchglas//<version>//DE
METHOD:PUBLISH
X-WR-CALNAME:Privat (busy)
REFRESH-INTERVAL;VALUE=DURATION:PT15M
X-PUBLISHED-TTL:PT15M
BEGIN:VEVENT
UID:<sha256(salt|start|end)[:32]>@milchglas
DTSTAMP:<last content change, not "now">
DTSTART:20260915T070000Z
DTEND:20260915T093000Z
SUMMARY:Blocker Privat
TRANSP:OPAQUE
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR
```

**Config (`config.json`, non-secret):** `tz`, `window_days` (28), `grid_minutes` (15), `summary`, `ttl_seconds` (900), `allday_mode`, `tentative_mode`, `owner_emails`, `calendars[] {href, name, enabled}`, `token` (MVP: single).
**Environment:** `CALDAV_URL`, `CALDAV_USER`, `CALDAV_SECRET`, `MILCHGLAS_VAR_DIR`, `MILCHGLAS_LOG_LEVEL`.

**Repository layout (proposed):**
```
milchglas/
├── CLAUDE.md  README.md  pyproject.toml
├── src/milchglas/{__main__.py, config.py, state.py, refresh.py}
├── src/milchglas/sources/{caldav.py, parse.py}
├── src/milchglas/core/{model.py, reduce.py, emit.py}
├── src/milchglas/web/{app.py, feed.py}          # WSGI; used by B (gunicorn) and C (Passenger); optional in A
├── tests/{unit, fixtures, contract}
├── deploy/{vps-systemd, docker-paas, shared-hosting-python, shared-hosting-php}   # one folder per Option
└── docs/{adr, runbook.md, consumers.md}
```

---

## 9. Deployment options

All four options share Sections 6–8 unless stated. Differences are in scheduling, serving, secrets, maintenance and security posture.

### Option A — Script as cron job or daemon on a Linux VPS
- **Shape:** Python package in a venv; `systemd` service + timer (every 15 min) or a `--loop` daemon; feed written to `/srv/milchglas/feed/<token>.ics`; served as a static file by Caddy (automatic TLS) or by the VPS's existing reverse proxy.
- **Prerequisites:** a VPS where ports 80/443 are free, or a route in an existing proxy. On a self-hosted PaaS host where Traefik (or a similar edge proxy) already owns 80/443, Option A there means either a file-provider route to a local port or a *second* small VPS (≈ €3–5/month).
- **Scheduling:** native cron/systemd timer — the simplest and most transparent mechanism of all options.
- **Secrets:** `EnvironmentFile=/etc/milchglas/env` (`0600`, root-owned); systemd hardening (`DynamicUser=yes`, `ProtectSystem=strict`, `ReadWritePaths=/srv/milchglas`, `IPAddressAllow=<nextcloud>` for egress, `PrivateTmp`, `NoNewPrivileges`).
- **Maintenance:** SSH + edit `config.json`; `systemctl start milchglas-refresh` to force a run; token rotation = rename file + update consumers.
- **Security posture:** strongest of all options (systemd sandbox, kernel-level egress allow-list, no container daemon).
- **Effort:** 1 evening if a VPS with free ports exists; +1 hour for Caddy/TLS.
- **Pros:** minimal moving parts; best hardening; no Docker.  **Cons:** awkward when the PaaS host already owns ports 80/443; a second VPS adds cost and upkeep; no Git-push deploys.

### Option B — Docker container(s) on a self-hosted PaaS (recommended for now)
- **Shape:** one image (`python:3.12-slim`, non-root UID, `read_only` FS, `tmpfs /tmp`, volume for state). Compose services: `web` (gunicorn serving `/f/<token>.ics` and `/healthz`) and `refresher` (`python -m milchglas refresh --loop --interval 900`). Traefik (or the PaaS's built-in proxy) provides TLS on an operator-chosen subdomain, e.g. `feed.example.org`.
- **Prerequisites:** DNS record for the chosen subdomain; the PaaS app created from the Git repo.
- **Scheduling:** in-container loop (or `supercronic`); lazy refresh in `web` as a safety net.
- **Secrets:** the PaaS's environment variables (encrypted at rest); never in the image.
- **Maintenance:** Git push → redeploy; `config.json` on the volume edited via the PaaS's terminal or a mounted file; `/healthz` wired to any HTTP uptime monitor.
- **Security posture:** good; egress restriction needs extra Docker network rules (optional); the PaaS and its edge proxy are already exposed anyway.
- **Effort:** 1 evening for MVP; matches a common self-hosting platform and mental model.
- **Pros:** fits a Docker/Git-based workflow already in place; Git-based deploys; logs and health in one place; stateless image makes migration a volume copy.  **Cons:** long-term availability of the current host is not guaranteed; Docker layer; per-app egress control is manual.

### Option C — Python script on shared web hosting (incl. website/UI)
- **Shape:** WSGI app under Phusion Passenger on a subdomain (`passenger_wsgi.py`, app root **outside** `httpdocs`). The same app serves the feed route *and* the maintenance website (Section 12, FR-17/18) — on this class of shared hosting this is not optional, because there is no other way to trigger Python: no CLI, no Python cron [FACT].
- **Prerequisites:** a hosting tier that includes Python support [VERIFY V-6]; pure-Python dependencies vendored by hand (no `pip`); env vars via the control panel if offered, else `0600` `.env` in the app root.
- **Scheduling:** *lazy refresh* on feed request when cache age > TTL, plus a shell cron `*/15 * * * * curl -fsS https://<host>/f/<token>.ics -o /dev/null` (shell cron is allowed; it keeps the cache warm and the Passenger process alive).
- **Secrets:** `.env` on a shared filesystem — weaker than A/B by nature.
- **Maintenance:** the in-app admin UI (auth per NFR-S6) is the primary maintenance channel; code updates via SFTP/Git; remember the *disable → enable* quirk after settings changes [REPORT].
- **Security posture:** shared hosting; no egress control, limited logs; mitigated by D-2 (read-only service user, revocable app password).
- **Effort:** 2–3 evenings (vendoring, Passenger quirks, admin UI becomes MVP-mandatory here).
- **Pros:** runs on web hosting many operators already have; needs no VPS; no Docker.  **Cons:** tariff dependency; hand vendoring; Passenger sandbox; admin UI is forced into MVP scope; shared filesystem for the secret.

### Option D — PHP application on shared web hosting
- **Shape:** PHP 8.x CLI script run by the hosting control panel's cron every 15 min (`php -f /…/milchglas/refresh.php`), writing `<token>.ics` into a subdomain docroot; served as a static file by Apache/nginx; optional admin page protected by directory protection (`.htaccess`) — Passenger is not involved, so directory protection works normally.
- **Prerequisites:** any shared-hosting tariff with PHP + cron + SSH included [FACT]; Composer via SSH (`php composer.phar require sabre/vobject`) for parsing and recurrence iteration, or rely on CalDAV server-side `expand` with a minimal hand-written parser.
- **Scheduling:** real cron — as clean as Option A.
- **Secrets:** `config.php` outside the docroot, `0600`; same shared-filesystem caveat as C.
- **Maintenance:** SFTP/Git + `.htaccess`-protected status page; token rotation = rename file.
- **Security posture:** as C, but a smaller runtime surface (no long-running app server, no custom auth code if `.htaccess` is used).
- **Effort:** 1–2 evenings; a *separate codebase* from A/B/C (port of `reduce`/`emit` with the same golden test fixtures).
- **Pros:** the natural fit for shared hosting — cron works, no tariff upgrade, no vendoring, no Passenger.  **Cons:** second language; the recurrence iterator library must be trusted (it is the same library the CalDAV server uses server-side — a reasonable trust anchor); divergence risk from the Python core.

### 9.1 Comparison

| Criterion | A · VPS script | B · PaaS Docker | C · shared-hosting Python | D · shared-hosting PHP |
|---|---|---|---|---|
| Scheduling | native timer ★ | in-container loop | lazy + curl cron | native cron ★ |
| Secrets at rest | root-owned env file, sandboxed ★ | PaaS env ★ | shared FS `.env` | shared FS config |
| Egress control | systemd IP allow-list ★ | manual Docker rules | none | none |
| Maintenance channel | SSH | Git push + terminal | in-app UI (mandatory) | SFTP + `.htaccess` page |
| Codebase | shared Python core | shared Python core | shared Python core | separate PHP port |
| Prerequisite risk | free ports / 2nd VPS | PaaS host not guaranteed long-term | sufficient hosting tier, `pip`-less | none |
| Effort to MVP | ~1 evening | ~1 evening | 2–3 evenings | 1–2 evenings |
| Portability of state | copy dir ★ | copy volume ★ | copy app root | copy dir |

### 9.2 Recommendation (for D-9)
1. **Now: Option B.** A single container host is the most common self-hosting setup, deploys by Git push, and keeps the Python core host-independent. Build the MVP there first.
2. **Keep the core deployable as Option A** (a `deploy/vps-systemd/` folder with unit files) — zero extra code, and it is the cleanest landing spot if the PaaS is ever dropped, whether on a new VPS or the same one without the PaaS.
3. **If shared hosting is a hard requirement, choose D over C.** Cron and static serving are first-class on shared hosting; Passenger-Python is not. Accept the PHP port and reuse the golden fixtures so both implementations must produce byte-identical feeds.
4. **Option C only** if Python on shared hosting is itself a goal (learning, consistency) — then the admin UI moves into MVP scope and a sufficient hosting tier is required.

---

## 10. Acceptance criteria

### 10.1 Gates before implementation (human-executed)
- **AC-0.1** A hand-written test feed (2 events, `REFRESH-INTERVAL:PT15M`) hosted on any HTTPS URL is successfully subscribed in mailbox.org and appears under *Meine Kalender*. Propagation time after editing an event is measured and recorded in `docs/consumers.md`. *(V-1)*
- **AC-0.2** The same feed connected in meetergo as an ICS calendar blocks a test slot in the booking page. *(V-5)*
- **AC-0.3** `svc-milchglas` exists; `PROPFIND` with its app password lists the shared calendars; a `calendar-query` with `expand` returns instances of a recurring test event including an overridden instance and an excluded date. *(V-2, V-4)*
- **AC-0.4** meetergo's booking horizon is confirmed ≤ `window_days`, or `window_days` is raised accordingly. *(Q-2)*

### 10.2 MVP functional
- **AC-1** Given three enabled calendars with overlapping events, when refresh runs, then the feed contains merged intervals only, and no interval overlaps or touches another.
- **AC-2** Given a weekly recurring event with one excluded date and one moved instance, the feed contains blocks for exactly the real occurrences within the window.
- **AC-3** Given events on the DST transition days of `Europe/Berlin`, local start/end times in the feed (converted from UTC) match the source.
- **AC-4** Given a cancelled event, a transparent event and an event the owner declined, none produces a block.
- **AC-5** Given an all-day event, the feed contains a `DATE`-valued all-day block (default mode).
- **AC-6** Given an unchanged source, two consecutive refreshes produce byte-identical feeds (same `UID`s, same `DTSTAMP`), and mailbox.org shows no duplicates after two refresh cycles. *(V-7)*
- **AC-7** Given the Nextcloud host is unreachable, the previous feed file remains byte-identical and `/healthz` turns 503 after 60 min.
- **AC-8** The feed body contains no property other than `UID, DTSTAMP, DTSTART, DTEND, SUMMARY, TRANSP, STATUS` (and the optional Microsoft busy hint); a test greps the output and every log line for any fixture title and finds none.
- **AC-9** `GET /f/<wrong-token>.ics` returns the same 404 body and timing class as any other unknown path; the correct token returns `200 text/calendar; charset=utf-8` with `ETag`.
- **AC-10** `config.json` edit (`enabled: false` on one calendar) + refresh removes that calendar's blocks; no restart needed.
- **AC-11** meetergo does not offer a slot that overlaps a private block; mailbox.org shows the block in the subscribed calendar within the measured propagation time.

### 10.3 MVP non-functional
- **AC-12** `ruff`, `mypy --strict`, `pytest` green in CI; runtime dependencies are pure Python.
- **AC-13** Container/process runs unprivileged; secret is not present in image layers, Git history or config file (CI secret scan).
- **AC-14** Runbook documents token rotation, calendar swap, stale recovery and host migration; each procedure has been executed once.

### 10.4 Later features (when pulled from backlog)
- **AC-15** (FR-15) After `stale_max_age`, the feed contains one all-day blocker per day in the window and `/healthz` reports fail-closed state.
- **AC-16** (FR-16) Rotating the `meetergo` token invalidates only meetergo's URL after the grace period; mailbox.org keeps working.
- **AC-17** (FR-17/18) Admin dashboard HTML contains no `DTSTART`/interval data; login lockout after 5 failures; CSRF rejected.
- **AC-18** (FR-19) With `free-busy-query`, a packet capture / debug log of the CalDAV exchange contains no `SUMMARY` lines.

---

## 11. Verification plan for assumptions

| ID | Assumption | Test | If false |
|---|---|---|---|
| V-1 | mailbox.org subscribes external ICS via *Von URL (iCal) importieren* and refreshes periodically | AC-0.1 | mailbox.org half unreachable via feed → FR-20 CalDAV push variant (Milchglas writes blocker VEVENTs into a dedicated mailbox.org calendar) |
| V-2 | Shared calendars are visible/readable to `svc-milchglas` via CalDAV | AC-0.3 | Check share flags, group app restrictions |
| V-3 | Nextcloud supports `free-busy-query` REPORT [LATER] | `curl -X REPORT` + PROPFIND `supported-report-set` | Stay on `calendar-query`; content transits memory only |
| V-4 | `calendar-query` + `expand` applies EXDATE and overridden instances correctly | AC-0.3 vs `recurring-ical-events` on the same fixture | Expand locally |
| V-5 | meetergo treats feed events as blocking without auth | AC-0.2 | Check per-calendar availability settings in meetergo |
| V-6 | Shared-hosting tariff with Python support in the control panel; `.env` readable by Passenger | control panel → Dev Tools | Option C infeasible → D or B |
| V-7 | Deterministic UIDs prevent duplicates in OX after refresh | AC-6 | Add `SEQUENCE`, adjust UID scheme |
| V-8 | On the self-hosted PaaS host, Traefik routes a subdomain to the container with TLS without manual Caddy | Deploy hello-world first | Fall back to Option A routing |

---

## 12. Concept ideas & backlog (not MVP)

| Idea | Value | Cost | Trigger to pull forward |
|---|---|---|---|
| **Free-busy-query acquisition** (FR-19) | Content never transits Milchglas — strongest privacy statement | 1 evening + V-3 | After MVP is stable |
| **Fail-closed blockers** (FR-15) | Outage cannot become double bookings | 1 hour | First time the feed was stale > 1 day |
| **Per-consumer tokens with rotation grace** (FR-16) | Attributable leaks, independent revocation | 2 hours | Third consumer or first suspected leak |
| **Admin UI** (FR-17/18) | Maintenance without SSH | 1–2 evenings | Third manual `config.json` edit, or Option C |
| **PROPFIND discovery + `missing` flag** | See withdrawn shares immediately | 1 hour | With admin UI |
| **All-day / tentative modes** (FR-13/14) | Birthdays should not block bookings | 1 hour | First lost booking due to an all-day event [OPEN Q-1] |
| **Per-source settings** | e.g. a vacation calendar's all-day events = busy, a family calendar's all-day events = ignore | 1 hour | With modes |
| **Mobile token** (ICSx5 / iOS subscription) | Busy overlay on phone despite OX DAV limitation | 30 min | If wanted [OPEN Q-5] |
| **Reverse WebCal** (Nextcloud subscribes mailbox.org `?ical=true`) | One private "everything" view — zero code | 5 min | Anytime |
| **CalDAV push into mailbox.org** (FR-20) | Independence from OX feed cache; works if V-1 fails | 1 evening | V-1 fails or cache interval unacceptable |
| **Baïkal contract tests in CI** | Protects recurrence handling on upgrades | 2 hours | Before first Nextcloud major upgrade |
| **Uptime monitor + e-mail alert** | Know about staleness before a client does | 15 min | With MVP deploy |
| **Option A unit files** | Post-migration landing spot | 30 min | Before moving off a PaaS host |

---

## 13. Open questions

| ID | Question | Default until answered |
|---|---|---|
| Q-1 | All-day events: block bookings (`busy`) or ignore? Should a dedicated out-of-office calendar be the only all-day source? | `busy` |
| Q-2 | meetergo booking horizon — is it ≤ 28 days? If not, what `window_days`? | 28 |
| Q-3 | Feed summary text and whether tentative appointments appear as a distinct "Vorläufig" | `Blocker Privat`, tentative = busy |
| Q-4 | Fail-closed threshold (when the feed is stale, how long until booking is blocked?) | 48 h (backlog) |
| Q-5 | Mobile subscription wanted in v1? | no |
| Q-6 | Hostname (operator-chosen subdomain?) and DNS location | an operator-chosen subdomain, e.g. `feed.example.org` |
| Q-7 | Runbook / consumer docs in German? | German |
| Q-8 | Deployment decision D-9: B now, A later? Or D because shared hosting must host it? | B |
| Q-9 | A timed busy block overlaps an all-day busy block: merge them into one, or keep both? | Keep both; the no-overlap, no-touch rule of AC-1 applies per kind |
| Q-10 | Tentative flag of a merged block when tentative and confirmed events overlap | Tentative only if every merged interval is tentative (the MVP emits tentative as plain busy, FR-14) |
| Q-11 | Does the owner's own `PARTSTAT=TENTATIVE` mark a block as tentative? | Yes, same as `STATUS:TENTATIVE` |
| Q-12 | Is an all-day event with `TRANSP:TRANSPARENT` excluded (FR-3 names no all-day exception)? | Excluded |
| Q-13 | Source and lifetime of the UID salt (ICS skeleton, Section 8) | A non-secret value generated once and stored in `config.json`; changing it changes every UID, so consumers see all blocks as new |
| Q-14 | One unparsable calendar object among valid ones: skip it or fail the refresh? | Fail the refresh and keep the last good feed (D-7d); skipping it would silently create a free slot |
| Q-15 | Retry backoff steps for FR-1 and the maximum response size | 1 s, 2 s, 4 s between the three retries; 16 MiB |
| Q-16 | Every enabled calendar answers successfully but holds no events: publish an empty feed? | Yes: publish a valid feed without events and record the success. Any failure (transport error, non-success status, unparsable body, unknown calendar) keeps the previous feed and never yields an empty one (D-7d, NFR-R1) |
| Q-17 | Response headers beyond NFR-S1: `X-Content-Type-Options: nosniff` and `Cache-Control: private, max-age=0` | Send both |
| Q-18 | What triggers local recurrence expansion (the FR-2 fallback)? | An explicit configuration setting, off by default; no automatic switch on a server error |

---

## 14. Sources consulted (2026-09-13)

- mailbox.org Knowledge Base — *FAQ zu Adressbüchern und Kalendern* (public share via `?ical=true`; calendars unencrypted); *Umzug von Posteo* article documenting *Von URL (iCal) importieren → iCal-Feed abonnieren*. https://kb.mailbox.org/de/privat/adressbuch-und-kalender/faq-zu-adressbuechern-und-kalendern/
- mailbox.org user forum — threads on iCal import errors and feed calendars not syncing via DAV.
- Open-Xchange App Suite middleware documentation — ICal calendar provider (caching, admin refresh interval, `REFRESH-INTERVAL` honoured, optional credentials).
- Nextcloud user manual (34) — calendar publishing and WebCal subscriptions. https://docs.nextcloud.com/server/latest/user_manual/en/groupware/calendar.html
- Nextcloud GitHub — calendar #171, #1044, #4044, #4086, #7694, #7846; server #10392, #10865, #60312. https://github.com/nextcloud/calendar/issues/7694
- Nextcloud community — "export free/busy only" support thread (NC 30, 2025): not possible.
- meetergo Help — *Kalender-Integrationen* and *ICS/iCal-Kalender verbinden* (updated 2026-01-08). https://help.meetergo.com/de/integrations/calendars/ · https://help.meetergo.com/de/integrations/calendars/connecting-ics-calendars/
- Shared web hosting provider Helpcenter — Python via Phusion Passenger only, on higher tiers; community reports on `pip` unavailability, disable→enable quirk, control-panel session timeout; tariff overview (SSH + cron in all tariffs).
- RFC 4791 (CalDAV: `calendar-query`, `expand`, `free-busy-query`), RFC 5545 (iCalendar).
- Prior art: `ical-filter-proxy` (freebusy_mode fork), keeper.sh, zeitfenster.

---

## 15. Glossary

- **Class-A content** — private event fields (title, description, location, attendees). Must never leave Nextcloud/Milchglas memory.
- **Busy pattern** — the set of anonymous intervals; personal data, minimised by window/grid/merge.
- **Capability URL** — a URL whose secret path is the credential.
- **Fail-closed** — on prolonged outage, block everything rather than nothing.
- **Service user** — `svc-milchglas`, the Nextcloud account holding only read-only shares.
