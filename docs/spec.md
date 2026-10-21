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

## 2. Goals and scope (MoSCoW)

One list, prioritised with MoSCoW. **Must** goals are the MVP (Section 6, "MVP" column). **Should** goals are MVP where Section 6 says so and otherwise follow it. **Could** goals are backlog (Section 12) and need an explicit maintainer decision before they are pulled forward. **Won't** items are out of scope; they were the non-goals of earlier drafts.

| ID | Priority | Goal | Specified in |
|---|---|---|---|
| G1 | Must | Publish an ICS feed that contains only busy intervals — no titles, descriptions, locations, attendees, categories, alarms | FR-4, FR-7, NFR-P3, AC-8 |
| G2 | Must | Feed is consumable by mailbox.org (OX iCal subscription) and by meetergo (read-only ICS calendar) | FR-7, FR-9, AC-0.1, AC-0.2, AC-11 |
| G3 | Must | Private event content never leaves Nextcloud; if it must transit Milchglas it is held in memory only, never persisted or logged | FR-4, NFR-P1, AC-8 |
| G4 | Must | Wrong intervals are prevented by design: recurrences, exceptions, DST and all-day events are handled correctly | FR-2, FR-3, FR-6, NFR-C1, AC-1 to AC-5 |
| G5 | Must | Fail-safe: a source outage never silently turns into "free" slots | FR-8, FR-11, NFR-R1, AC-7 |
| G6 | Must | Operable by one person in the evening without on-call: boring technology, one config file, one log | NFR-O1, NFR-O2, AC-14 |
| G7 | Should | Maintenance without touching secrets: swap/enable/disable source calendars, rotate the feed URL, force a refresh (MVP via config file; UI later) | FR-12, AC-10; FR-17, FR-18 |
| G8 | Should | Host-portable: the same core code runs under Options A, B and C (Section 9) | NFR-O3, Section 9 |
| G9 | Should | Data minimisation of the busy pattern itself: short window, rounding, merging | NFR-P2, FR-5, FR-6 |
| G10 | Could | Content never transits Milchglas: busy times are acquired with `free-busy-query` | FR-19, V-3 |
| G11 | Could | A prolonged source outage blocks bookings instead of leaving a stale feed (fail-closed) | FR-15, NFR-R3, Q-4 |
| G12 | Could | Leaks are attributable and revocable per consumer | FR-16 |
| G13 | Could | Maintenance without SSH: admin UI with calendar discovery | FR-17, FR-18, NFR-S6 |
| G14 | Could | All-day and tentative handling per mode and per source calendar | FR-13, FR-14, Q-1 |
| G15 | Could | Busy overlay on the operator's phone through a feed subscription | Q-5 |
| G16 | Could | Independence from the mailbox.org feed cache by writing blocks via CalDAV | FR-20, V-1 |
| W1 | Won't | Two-way sync or writing into any calendar (bookings continue to flow meetergo → mailbox.org) | |
| W2 | Won't | Replacing meetergo, Nextcloud Appointments or OX scheduling | |
| W3 | Won't | Multi-tenant or multi-user operation | |
| W4 | Won't | Mobile push; phones may subscribe to the same feed (G15) | |
| W5 | Won't | Encrypting the feed for consumers (meetergo requires public URLs [FACT]; OX credential support for feeds is unverified) | |
| W6 | Won't | Protecting against the providers themselves (the Nextcloud host, the PaaS/hosting provider, mailbox.org, meetergo) seeing what they legitimately process | |

## 3. Limits, operation and expected load

### 3.1 Known limitations

What Milchglas cannot promise, by design or because of the platforms it connects. Open questions in Section 13 may narrow some of these; none of them is a defect to be fixed in the MVP.

| ID | Limitation | Consequence | Reference |
|---|---|---|---|
| L1 | Not real time. A change reaches the feed within one refresh interval (15 min) and each consumer after its own polling: meetergo usually shows changes within 5–10 min and re-checks the calendar before it confirms a booking [FACT]; Open-Xchange refreshes a feed calendar every 7 days by default, waits one hour after a failed fetch, and honours `REFRESH-INTERVAL` [FACT] — whether mailbox.org keeps that behaviour is V-1 | About 25 min until meetergo blocks a new private appointment; the mailbox.org view can lag longer (measured in AC-0.1) | FR-10, V-1, AC-0.1, AC-11 |
| L2 | Blocks exist only from today 00:00 to today + `window_days`. meetergo starts every new meeting type with a 30-day booking window [FACT] | Days beyond the window are bookable unless every meeting type's window fits inside it | FR-5, D-6, Q-2, AC-0.4 |
| L3 | Blocks are rounded to the grid (15 min) and merged | Up to one grid step minus one minute of extra busy time at each block edge; adjacent appointments appear as one block | FR-6, G9 |
| L4 | One shared feed token until FR-16 | A leak cannot be attributed to one consumer, and a rotation cuts off both consumers at once | NFR-S1, G12 |
| L5 | Nextcloud skips objects it cannot parse and recurring series beyond 3500 iterations, and still answers `207 Multi-Status` [FACT] | Milchglas cannot see these drops; such an event yields no block | FR-1, Q-14, Q-16 |
| L6 | The read-only service user never sees `CLASS:PRIVATE` events and receives `CLASS:CONFIDENTIAL` events without `STATUS`, `TRANSP` and `ATTENDEE` [FACT] | Private events yield no block (D-3); confidential events always block, even when cancelled, transparent or declined | D-3, FR-3 |
| L7 | The service credential reads the full content of every `CLASS:PUBLIC` event in the shared calendars [FACT] | A leaked app password discloses content, not only busy times; D-2 bounds write access, not read access | D-2, NFR-S3 |
| L8 | Event content transits refresher memory on every run | Only G10 removes the transit | G3, FR-19 |
| L9 | The capability URL is the only credential for the feed | Anyone holding the URL sees the busy pattern of the window | NFR-S1, W5 |
| L10 | Python 3.12 receives security fixes until about October 2028 [FACT] | A move to a newer Python minor release is due before then | D-12, NFR-O3 |

### 3.2 Operating requirements

What the operator provides and keeps running. Values are for Option B (Section 9) unless stated.

| ID | Requirement | Why | Reference |
|---|---|---|---|
| OR1 | A container host with a persistent volume, Compose support and an edge proxy with automatic TLS; about 150 MB of free memory for the two services | Runs `web` and `refresher` and keeps the feed and state across deploys | Section 9 Option B, Section 3.3 |
| OR2 | A DNS record for the feed host, ports 80/443 reachable at the proxy, a certificate from a public CA | Both consumers fetch the feed over HTTPS from the Internet | FR-9, Q-6 |
| OR3 | The Nextcloud service user `svc-milchglas` with read-only shares only, quota `0 B` (the value `none` means unlimited), and an app password that can be revoked in one click | Least privilege on the source side | D-2, NFR-S3, AC-0.3 |
| OR4 | `CALDAV_URL`, `CALDAV_USER` and `CALDAV_SECRET` set as platform environment variables. The platform host is trusted with them: Coolify, for example, writes them into a plaintext `.env` on the server at deploy time [FACT] | No secret in Git, image or `config.json` | D-11, NFR-S2 |
| OR5 | Proxy and platform access logs never record the feed path. Traefik can drop the request path field or disable access logs per router, but cannot hash it [FACT] | The path carries the token | NFR-S5 |
| OR6 | An external uptime monitor polls `/healthz` and alerts the operator by e-mail | A stale feed must not go unnoticed | NFR-R2, FR-11 |
| OR7 | An accurate host clock (NTP) | The window starts at "today 00:00" in `tz` | FR-5 |
| OR8 | Outbound HTTPS from the refresher to the Nextcloud host | Data source | FR-1, NFR-S4 |
| OR9 | Backup of `config.json` and the state directory before a host migration | Losing the UID salt changes every UID, and consumers then replace all blocks | NFR-O2, Q-13 |
| OR10 | The consumers are set up once: a feed subscription in mailbox.org, and an ICS calendar in meetergo for every meeting type in use | Both consumers must read the feed | AC-0.1, AC-0.2, AC-0.4 |
| OR11 | Operator time: about one evening for setup; no routine work; the runbook on an alert, a token rotation or a host move | One person, no on-call | G6, NFR-O2, Section 9 |

### 3.3 Expected load and performance

Milchglas serves one operator; scaling beyond these figures is not a goal (W3). *Derived* values follow from the parameters in this spec, *measured* values come from local probes or registries on 2026-10-21, and *target* values are design limits that AC-0.3 and the first week of operation confirm.

| Quantity | Value | Basis |
|---|---|---|
| Users | 1 operator; 2 consumers (mailbox.org, meetergo); optionally a third, a phone subscription (Q-5) | Section 1, W3 |
| Enabled source calendars | ≤ 10 | target |
| Event instances in the window after expansion | ≤ 1 000 | target; AC-0.3 records the instance count and the response size |
| CalDAV response size | well below 1 MiB per calendar; hard limit 16 MiB | target; Q-15 |
| Refresh runs | 96 per day (every 15 min) | derived, FR-10 |
| Refresh run duration | a few seconds when healthy; at most about 47 s per unreachable calendar (4 attempts × 10 s timeout plus 1 + 2 + 4 s backoff) | derived, FR-1, Q-15 |
| Feed requests | about 100–400 per day (≈ 0.005 req/s): mailbox.org at most 96 at `PT15M`, meetergo on its own sync cycle | derived, L1 |
| Feed size | about 0.2 KB per block, about 200 KB at 1 000 blocks | derived from the skeleton in Section 8 |
| Response time of `/f/<token>.ics` and `/healthz` | < 100 ms at the proxy; one synchronous worker then serves about 10 req/s, more than 1 000 times the expected load | target |
| Memory | about 39 MB per Python process with the runtime libraries loaded (macOS arm64; Linux figures differ); about 80–120 MB for `web` and `refresher` together | measured; estimate |
| Container base image | `python:3.12-slim`, about 43 MB compressed | measured (registry) |
| Freshness | private change → feed ≤ 15 min; → meetergo ≈ 25 min; `/healthz` turns 503 after 60 min without a successful refresh | derived, FR-10, FR-11, L1 |

---

## 4. Research findings (as of 2026-09-13, corrected 2026-10-21)

### 4.1 Nextcloud
- Calendars can be published via a public read-only link; `?export` yields ICS **with full details** for `CLASS:PUBLIC` events (the default); `CLASS:CONFIDENTIAL` events are redacted to "Busy" and `CLASS:PRIVATE` events are omitted [FACT].
- No calendar-level "share/export busy only" exists; the feature request server #11214 is open since 2018-09-14, and the older calendar #171 (closed as won't-implement, 2016) and #1044 (closed 2019) are superseded [FACT].
- Per-event visibility exists: *Show full event* (`CLASS:PUBLIC`, default) / *When shared show only busy* (`CLASS:CONFIDENTIAL`) / *Hide* (`CLASS:PRIVATE`). There is no per-calendar default; every event must be set manually (server #11214; calendar #4086 was closed as its duplicate) [FACT].
- Visibility depends on the share permission. Read-only sharees get `CLASS:CONFIDENTIAL` events as "Busy", with `STATUS`, `TRANSP` and `ATTENDEE` removed, and never see `CLASS:PRIVATE` ones [FACT, server source v35.0.1]. Writable sharees see full events since server PR #54533 (Aug 2025, backported to 30 and 31), which also fixed the title overwrite of calendar #4044 [FACT]. The CalDAV-vs-web mismatch of server #10392 was fixed in 2018 (PR #12458) [FACT, historical]. Calendar #7694 (Nov 2025, "all group sharees see full data") is an unconfirmed report that a commenter ties to write access [REPORT]. Invited attendees get details through the invitation, while the shared view stays busy-only (calendar #7846) [REPORT].
- No public or unauthenticated free/busy export exists; free/busy lookups in the UI work only inside the same instance [REPORT, community thread]. An authenticated sharee can run the RFC 4791 `free-busy-query` REPORT inherited from sabre/dav [FACT, source level; live check V-3].
- Nextcloud can *subscribe* to external WebCal/ICS feeds (reverse direction is free) [FACT].
- Nextcloud Appointments conflict detection silently ignores subscribed ICS feeds (calendar #8446, transferred from server #60312; `CalendarProvider` reads only the user's calendars, never subscriptions) [FACT, source level] — relevant only if meetergo were ever replaced.
- **Design consequence [DECIDED D-3]:** Nextcloud sharing is used for *least privilege* (read-only service user), never for redaction. Redaction happens in Milchglas. `CLASS:PRIVATE` must never be used on private events — hidden events would become bookable slots.

### 4.2 mailbox.org / Open-Xchange
- External iCal feeds **can** be subscribed in the web client: arrow next to *Neuer Termin* → *Von URL (iCal) importieren* → dialog *iCal-Feed abonnieren* → calendar appears under *Meine Kalender* [FACT, mailbox.org KB migration article]. The current KB FAQ no longer states otherwise (checked 2026-10-21); the refresh interval and credentials remain to be confirmed by test [VERIFY V-1].
- OX's ICal calendar provider caches feeds server-side; the refresh interval is admin-configured and a feed's `REFRESH-INTERVAL` is honoured [FACT, OX middleware docs]. OX defaults: `com.openexchange.calendar.ical.refreshInterval` 10080 min (7 days), `retryAfterErrorInterval` 3600 s (a failed fetch pauses refreshes for an hour), maximum feed size 5 MB [FACT, OX 8.54 property reference]. Whether mailbox.org honours a PT15M `REFRESH-INTERVAL` is unknown [VERIFY V-1].
- Whether optional HTTP credentials can be entered for a feed at mailbox.org is unknown (OX supports it in principle) [VERIFY V-1].
- Public share links (`?ical=true`) are read-only; anyone with the link sees all content of standard-visibility appointments, while private-classified appointments show non-participants only times and "Private" [FACT, OX docs; the anonymous link export itself is untested].
- Subscribed feed calendars may not sync to phones through mailbox.org's CalDAV [REPORT, user forum; not re-found 2026-10-21]. The OX default `com.openexchange.calendar.ical.usedForSync=true` offers them over CalDAV unless the operator disables it [FACT]; mailbox.org's value is unknown.
- Calendars are not encrypted at rest [FACT] — an argument for never storing private titles there.

### 4.3 meetergo
- Connects Nextcloud via CalDAV, mailbox.org via generic CalDAV, and any ICS/iCal link read-only for availability checks; bookings are not written to ICS calendars [FACT, help.meetergo.com, updated 2026-01].
- ICS URLs must be publicly reachable; private and local addresses are rejected [FACT]. For services that require authentication, meetergo advises their public sharing option instead, so authenticated feeds are not supported in practice [FACT, help page wording].
- Multiple connected calendars are all checked for conflicts; per-calendar "read appointments" toggles exist [FACT].
- Refresh cadence described as "regelmäßig"; changes usually sync within 5-10 minutes, a manual refresh exists, and meetergo re-checks the calendar before confirming a booking and refuses the booking if that check fails. On a failed update it keeps the busy times it loaded last; with no stored data it blocks the host's time [FACT, help.meetergo.com, 2026-07-28].

### 4.4 Shared web hosting (Passenger-based)
- Python runs **only** as WSGI apps under Phusion Passenger; no CLI, no SSH Python, no Python cron [FACT, hosting provider Helpcenter].
- Python/Node/Ruby are available only from a higher hosting tier upward [FACT].
- `pip` is not usable, because Python cannot run via CLI, SSH or cron (derived from the [FACT] above; one community report agrees); packages must be uploaded [REPORT].
- SSH access and (shell/PHP) cron jobs are included in all tariffs; the entry tariff allows one cron job [FACT].
- Changed Python settings only apply after *disable → enable* [FACT, German Helpcenter page; the English page says "after an application restart"]; the control-panel session expires silently after ~15 min [REPORT].
- Panel generation differs by package age; the operator's specific package must be checked [VERIFY V-6]. These facts describe the provider inferred from the traits above; V-6 records which provider it is.

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
| D-12 | Implementation language for the MVP: Python 3.12 (NFR-O3); a rewrite (e.g. Go) is evaluated only after the MVP works and is deployed (Section 12) | Decided 2026-10-21 | Toolchain, gates and test plan exist in Python; an evaluation of Go for testability, scalability, extensibility and security found no gain for the MVP that outweighs switching now |

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
| **Rewrite evaluation** (D-12) | Single static binary, smaller image and memory footprint; possibly one codebase for shared hosting instead of the Option D port | Open until evaluated; a rewrite reuses the golden fixtures (NFR-C1) as its parity check | MVP works and is deployed |

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
- Nextcloud GitHub — server #11214 (open busy-only request), PR #54533, PR #12458, #10392 (fixed 2018); calendar #171, #1044, #4086 (closed), #4044 (fixed 2025), #7694, #7846, #8446 (was server #60312). https://github.com/nextcloud/server/issues/11214 · https://github.com/nextcloud/calendar/issues/7694
- Nextcloud community — "export free/busy only" support thread (NC 30, 2025): not possible.
- meetergo Help — *Kalender-Integrationen* and *ICS/iCal-Kalender verbinden* (updated 2026-01-08). https://help.meetergo.com/de/integrations/calendars/ · https://help.meetergo.com/de/integrations/calendars/connecting-ics-calendars/
- Shared web hosting provider Helpcenter — Python via Phusion Passenger only, on higher tiers; settings apply after disable→enable (German page); one community report on `pip`; community reports on the control-panel session timeout; tariff overview (SSH + cron in all tariffs, one cron job on the entry tariff).
- RFC 4791 (CalDAV: `calendar-query`, `expand`, `free-busy-query`), RFC 5545 (iCalendar), RFC 7986 (updates RFC 5545: `REFRESH-INTERVAL`, `NAME`); `X-PUBLISHED-TTL` and `X-WR-CALNAME` are vendor extensions (MS-OXCICAL).
- Prior art: `ical-filter-proxy` (freebusy_mode fork, https://github.com/fvoges/ical-filter-proxy), keeper.sh (https://github.com/ridafkih/keeper.sh), zeitfenster (https://github.com/Embedded-Focus/zeitfenster).

**Added 2026-10-21** (validation of the research claims; sources for Section 3):

- meetergo Help — *Buchungen in der Zukunft begrenzen* (updated 2026-08-04; new meeting types start at 30 calendar days). https://help.meetergo.com/de/scheduling/meeting-types/limit-future-bookings/
- meetergo Help — why calendar events do not block availability (changes sync within 5–10 min; re-check before a booking is confirmed). https://help.meetergo.com/de/scheduling/availability/why-are-events-in-my-calendar-not-blocking-my-availability/
- Open-Xchange middleware configuration properties, version 8 (`refreshInterval` default 10080 min, `retryAfterErrorInterval` 3600 s). https://documentation.open-xchange.com/components/middleware/config/8/properties.json
- Nextcloud server v35.0.1 — `apps/dav/lib/CalDAV/` (`CalDavBackend::calendarQuery` skips unparsable and over-limit objects; `CalendarObject` and `Calendar` redact or hide events for sharees) and `lib/private/User/User.php` (quota values). https://github.com/nextcloud/server/tree/v35.0.1/apps/dav/lib/CalDAV
- sabre/vobject 4.5.6 — `Settings::$maxRecurrences` (3500); `Recur/EventIterator` (expanded instances keep `DURATION` with a UTC `DTSTART`). https://github.com/sabre-io/vobject/blob/4.5.6/lib/Settings.php · https://github.com/sabre-io/vobject/blob/4.5.6/lib/Recur/EventIterator.php
- Coolify v4.4.6 — `ApplicationDeploymentJob` writes runtime variables into the application's `.env` on the server. https://github.com/coollabsio/coolify/blob/v4.4.6/app/Jobs/ApplicationDeploymentJob.php
- Traefik — access logs (fields can be dropped, access logs disabled per router). https://doc.traefik.io/traefik/reference/install-configuration/observability/logs-and-accesslogs/
- PEP 693 — Python 3.12 release schedule (security fixes until about October 2028). https://peps.python.org/pep-0693/
- Re-validation 2026-10-21: Nextcloud server source at v35.0.1, sabre/dav 4.7.0, sabre/vobject 4.5.6 (the versions Nextcloud 33–35 pin, `nextcloud/3rdparty` `composer.lock`); OX middleware property reference 8.54.465; Phusion Passenger docs (environment variables, PassengerPoolIdleTime); systemd.exec and systemd.resource-control (systemd 262); W3C TAG "Good Practices for Capability URLs" (First Public Working Draft, 2014). https://www.phusionpassenger.com/library/indepth/environment_variables.html · https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html · https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html · https://www.w3.org/TR/capability-urls/
- Nextcloud administration manual — brute-force protection (failures are delayed, then answered with `429`). https://docs.nextcloud.com/server/latest/admin_manual/configuration_server/bruteforce_configuration.html
- Calendar client defaults for all-day events: Thunderbird (pref `calendar.events.defaultTransparency.allday.transparent`, written as `TRANSPARENT`), Microsoft Outlook support (classic Outlook shows new all-day events as free), Nextcloud Calendar and OX (busy); RFC 5545 section 3.8.2.7 (`TRANSPARENT` is invisible to busy-time searches). https://support.microsoft.com/en-us/outlook/calendar/change-an-appointment-meeting-or-event-in-outlook
- RFC 5545 sections 3.1 (lines over 75 octets: SHOULD NOT), 3.2.12 (PARTSTAT defaults to NEEDS-ACTION), 3.3.5 (a local time in a DST gap takes the pre-gap offset), 3.3.6 (nominal days and weeks), 3.3.11 (TEXT escaping), 3.8.7.2 (DTSTAMP with and without `METHOD`); RFC 5321 (case-sensitive local part); RFC 8657 (CAA `accounturi`).
- icalendar 7.3.0 — `vText` turns a literal `\N` into a newline when parsing. https://pypi.org/project/icalendar/7.3.0/
- gunicorn settings — control socket (on by default since 25.1.0), access log (off by default). https://gunicorn.org/reference/settings/#control_socket
- Docker — packet filtering and firewalls (`DOCKER-USER`; no per-container egress filter by default). https://docs.docker.com/engine/network/firewall-iptables/
- Trivy — secret scanning of image layers and image configuration (`--image-config-scanners secret`); advisory GHSA-69fq-xp46-6x23 (its GitHub Actions compromised on 2026-03-19). https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23
- `ckulka/baikal` container image (Baïkal 0.10.1, sabre/dav ~4.7.0; php8.2 variant). https://github.com/ckulka/baikal-docker
- Atheris 3.1.0 (wheels for cp312–cp314 manylinux x86_64 only, no sdist). https://pypi.org/project/atheris/3.1.0/#files
- OWASP Cheat Sheet Series — Password Storage, Authentication, Cross-Site Request Forgery Prevention. https://github.com/OWASP/CheatSheetSeries

---

## 15. Glossary

- **Class-A content** — private event fields (title, description, location, attendees). Must never leave Nextcloud/Milchglas memory.
- **Busy pattern** — the set of anonymous intervals; personal data, minimised by window/grid/merge.
- **Capability URL** — a URL whose secret path is the credential.
- **Fail-closed** — on prolonged outage, block everything rather than nothing.
- **Service user** — `svc-milchglas`, the Nextcloud account holding only read-only shares.
