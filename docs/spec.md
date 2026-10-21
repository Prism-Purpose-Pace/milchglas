# Milchglas — Product Requirements (v0.4)

> v0.3 is the public edition of the internal v0.2 draft: product renamed, operator-specific details removed.
> v0.4 adds Sections 2–3 (MoSCoW goals, limits, operation, load) and applies the 2026-10-21 re-validation: corrected findings and sources, a 33-day window, a hashed feed token, decisions D-12 to D-15, open questions Q-9 to Q-22, NFR-P4, NFR-S7, AC-19 to AC-22 and V-9.

**Status:** Draft · **Date:** 2026-10-21 · **Supersedes:** Architecture & Implementation Concept v0.1 (2026-09-13), now folded into Sections 7, 9 and 12 of this PRD.

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
| G3 | Must | Private event content never leaves Nextcloud; if it must transit Milchglas it is held in memory only, never persisted or logged. The service credential itself can read that content (D-2) | FR-4, NFR-P1, NFR-P4, AC-8 |
| G4 | Must | Wrong intervals are prevented by design: recurrences, exceptions, DST and all-day events are handled correctly | FR-2, FR-3, FR-6, NFR-C1, AC-1 to AC-5, AC-22 |
| G5 | Must | Fail-safe: a source outage never silently turns into "free" slots; residual: objects Nextcloud drops server-side (L5) | FR-8, FR-11, NFR-R1, Q-16, AC-7, AC-19 |
| G6 | Must | Operable by one person in the evening without on-call: boring technology, one config file, one log | NFR-O1, NFR-O2, AC-14 |
| G7 | Should | Maintenance without touching secrets: swap/enable/disable source calendars, rotate the feed URL, force a refresh (MVP via config file and CLI; UI later) | FR-12, AC-10, AC-20; FR-17, FR-18 |
| G8 | Should | Host-portable: the same core code runs under Options A, B and C (Section 9) | NFR-O3, Section 9 |
| G9 | Should | Data minimisation of the busy pattern itself: short window, rounding, merging | NFR-P2, FR-5, FR-6, Q-22 |
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
| L2 | Blocks exist only from today 00:00 to today + `window_days`. meetergo starts every new meeting type with a 30-day booking window [FACT] | The default of 33 days covers that window with a two-day buffer for refresher outages; days beyond the window are bookable unless every meeting type's window is at most `window_days` - 3 | FR-5, D-6, Q-2, AC-0.4 |
| L3 | Blocks are rounded to the grid (15 min) and merged | Up to one grid step minus one minute of extra busy time at each block edge; adjacent appointments appear as one block | FR-6, G9 |
| L4 | One shared feed token until FR-16 | A leak cannot be attributed to one consumer, and a rotation cuts off both consumers at once | NFR-S1, G12, Q-21 |
| L5 | Nextcloud skips objects it cannot parse and recurring series beyond 3500 iterations, and still answers `207 Multi-Status` [FACT]. Per the sabre/vobject 4.5.6 source, the `time-range` filter and `expand` also drop, without error, an object that holds only an unmoved overridden instance and no master, an RDATE-only series whose first instance precedes the window, and every RRULE instance of a series that also has an `RDATE`; the skip-on-error behaviour exists only because the request carries a `time-range` | Milchglas cannot see these drops; such an event yields no block. The Q-16 warnings and the runbook's server-log check reduce, not remove, the risk; AC-0.3 pins each drop, and a reproduced drop fails V-4 | FR-1, Q-14, Q-16, NFR-O2, V-4 |
| L6 | The read-only service user never sees `CLASS:PRIVATE` events and receives `CLASS:CONFIDENTIAL` events without `STATUS`, `TRANSP` and `ATTENDEE` [FACT]. Nextcloud matches `CLASS` case-sensitively: any value other than exactly `PUBLIC` or `CONFIDENTIAL` (for example `confidential` or `X-FOO`) is stored as private, and the master's class decides for the whole object [FACT] | Private events, and events with any other `CLASS` value, yield no block (D-3); confidential events always block, even when cancelled, transparent or declined | D-3, FR-3, NFR-O2 |
| L7 | The service credential reads the full content of every `CLASS:PUBLIC` event in the shared calendars [FACT] | A leaked app password discloses content, not only busy times; D-2 bounds write access, not read access | D-2, NFR-S3 |
| L8 | Event content transits refresher memory on every run | Only G10 removes the transit | G3, FR-19 |
| L9 | The capability URL is the only credential for the feed | Anyone holding the URL sees the busy pattern of the window | NFR-S1, W5 |
| L10 | Python 3.12 receives security fixes until about October 2028 [FACT] | A move to a newer Python minor release is due before then | D-12, NFR-O3 |
| L11 | On the `expand` path Nextcloud reads floating times in the calendar's `calendar-timezone`, and as UTC when the calendar has none [FACT] | A floating 09:00 event in a calendar without `calendar-timezone` is published at 09:00Z, one or two hours off in `Europe/Berlin`; AC-0.3 records the property per calendar | FR-2, Q-18, AC-0.3 |

### 3.2 Operating requirements

What the operator provides and keeps running. Values are for Option B (Section 9) unless stated.

| ID | Requirement | Why | Reference |
|---|---|---|---|
| OR1 | A container host with a persistent volume, Compose support and an edge proxy with automatic TLS; about 150 MB of free memory for the two services | Runs `web` and `refresher` and keeps the feed and state across deploys | Section 9 Option B, Section 3.3 |
| OR2 | A DNS record for the feed host, ports 80/443 reachable at the proxy, a certificate from a public CA | Both consumers fetch the feed over HTTPS from the Internet | FR-9, Q-6 |
| OR3 | The Nextcloud service user `svc-milchglas` with read-only shares only and quota `0 B` (the value `none` means unlimited); it is no calendar delegate (proxy) of the owner and belongs to no group a calendar is shared with, because the more permissive share wins; the FR-1 check fails the refresh on a writable share. Setup needs admin rights and a free user seat. The system address book is hidden (`occ config:app:set dav system_addressbook_exposed --value=false`). The app password is created in the service user's own login, which always grants filesystem access; that access is removed right after creation. The app password can be revoked in one click | Least privilege on the source side | D-2, NFR-S3, AC-0.3 |
| OR4 | `CALDAV_URL`, `CALDAV_USER` and `CALDAV_SECRET` set as platform environment variables for the `refresher` only (D-13). The platform host is trusted with them: Coolify, for example, writes them into a plaintext `.env` on the server at deploy time [FACT] | No secret in Git, image or `config.json` | D-11, NFR-S2 |
| OR5 | Proxy and platform access logs never record the feed path. Traefik can drop the request path field or disable access logs per router, but cannot hash it [FACT] | The path carries the token | NFR-S5, AC-21 |
| OR6 | An external uptime monitor polls `/healthz` at least every 5 minutes and alerts the operator by e-mail | A stale feed must not go unnoticed | NFR-R2, FR-11, AC-19 |
| OR7 | An accurate host clock (NTP) | The window starts at "today 00:00" in `tz` | FR-5, NFR-O2 |
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
| Refresh run duration | a few seconds when healthy; at most about 47 s per unreachable calendar (4 attempts × 10 s timeout plus 1 + 2 + 4 s backoff; `401`, `403` and `429` are not retried); every run ends at the 120 s total deadline | derived, FR-1, Q-15, NFR-S7 |
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
- **Design consequence [DECIDED D-3]:** Nextcloud sharing is used for *least privilege* (read-only service user), never for redaction. Redaction happens in Milchglas. `CLASS:PRIVATE` must never be used on private events — hidden events would become bookable slots. Do not rely on `CLASS:CONFIDENTIAL` either: for the read-only service user Nextcloud removes `STATUS`, `TRANSP` and `ATTENDEE` from confidential events, so cancelled, transparent, tentative and owner-declined confidential events still block.

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
| D-2 | Nextcloud access via a dedicated service user `svc-milchglas` with read-only shares, zero quota, revocable app password | Decided; rationale corrected 2026-10-21 | Least privilege. A leaked app password reads every event in the shared calendars in full except `CLASS:PRIVATE` ones (`CLASS:PUBLIC` is the default; read-only sharees see `CLASS:CONFIDENTIAL` as busy) and, unless disabled, the system address book. It can write only to the service user's own, empty calendar home, never to a shared calendar or to files. Revocation is one click (NFR-S3). |
| D-3 | Redaction happens exclusively in Milchglas; never rely on Nextcloud `CLASS`; never use `CLASS:PRIVATE` on private events | Decided; consequence added 2026-10-21 | Enforcement bugs (4.1); hidden events create false-free slots. Do not rely on `CLASS:CONFIDENTIAL` either: for the read-only service user Nextcloud removes `STATUS`, `TRANSP` and `ATTENDEE` from confidential events, so cancelled, transparent, tentative and owner-declined confidential events still block. |
| D-4 | Both consumers (mailbox.org, meetergo) subscribe to the Milchglas feed; Nextcloud is **not** connected to meetergo directly | Decided | Data minimisation toward the third-party processor |
| D-5 | MVP first (a small pure core + cron + feed behind HTTPS); v0.1 concept features become backlog | Decided 2026-09-13; wording aligned 2026-10-21 (the feed is served through the WSGI app, D-14; the line estimate is dropped) | The maintainer's challenge was correct: most of v0.1 is optional; four items are not (D-7) |
| D-6 | Window: today → +33 days (meetergo's default booking window of 30 calendar days, today, and a two-day buffer for refresher outages) | Proposed; confirm [OPEN Q-2] | Covers the booking horizon with a staleness margin; shorter windows leave bookable days |
| D-7 | Mandatory even in MVP: (a) correct recurrence expansion, (b) merged intervals (set union), (c) deterministic UIDs, (d) never overwrite the last good feed on failure | Decided | Correctness and safety, not architecture |
| D-8 | Output as `VEVENT`s in UTC, all-day as `DATE`, `SUMMARY` "Blocker Privat" (configurable), `TRANSP:OPAQUE` | Proposed; decided after AC-0.1 and AC-0.2 pass with the shipped header and one `VALUE=DATE` block | OX and meetergo consume VEVENTs; UTC avoids VTIMEZONE; stable UIDs prevent OX churn. Without `METHOD`, RFC 5545 section 3.8.7.2 defines DTSTAMP as the last revision of the component, which is what Milchglas emits (D-7c). If either consumer rejects the `METHOD`-less header in AC-0.1 or AC-0.2, `METHOD:PUBLISH` returns and D-7c records that a regenerated, byte-identical feed is the same object instance. |
| D-9 | Deployment target | **Open — see Section 9**; recommendation: Option B now | |
| D-10 | Documentation language English; runbook may be German | Proposed [OPEN Q-7] | Maintainer defaults |
| D-11 | Secrets only via environment (or `0600` file); never entered or shown in any UI | Proposed | Avoids crypto dependency; standard on self-hosted PaaS platforms |
| D-12 | Implementation language for the MVP: Python 3.12 (NFR-O3); a rewrite (e.g. Go) is evaluated only after the MVP works and is deployed (Section 12) | Decided 2026-10-21 | Toolchain, gates and test plan exist in Python; an evaluation of Go for testability, scalability, extensibility and security found no gain for the MVP that outweighs switching now |
| D-13 | `web` serves files only: no lazy refresh, no CalDAV credential; it refuses to start when a `CALDAV_*` variable is set | Decided 2026-10-21 | The Internet-facing process holds neither the CalDAV credential nor event content; the uptime monitor (AC-19) covers a dead refresher. Option C keeps its lazy refresh because Passenger offers no other trigger |
| D-14 | Feed token stored as SHA-256 only (`token_sha256` in `config.json`); generated and rotated by the CLI (`init`, `rotate-token`); applies to the shared Python core (Options A–C) | Decided 2026-10-21 | A plaintext token in the shareable `config.json` travels into bug reports, backups and support chats; a digest allows rotation without restart and keeps the token out of file names. A lost token cannot be recovered; `rotate-token` replaces it |
| D-15 | No publication on PyPI; installs come only from verified release assets; installing by package name is documented as unsafe | Decided 2026-10-21 | The running code must match an attested release; the package name was unregistered on 2026-10-21, so an install by name could fetch someone else's package; a publishing pipeline adds upkeep with no consumer |

---

## 6. Functional requirements

| ID | Requirement | MVP | Later |
|---|---|---|---|
| FR-1 | Read all *enabled* calendars of the service user via CalDAV: one `REPORT` per calendar href with `Depth: 1` and a `calendar-query` body (a `VCALENDAR` comp-filter around a `VEVENT` comp-filter with a `time-range` over the window, and `calendar-data` with `expand` over the same range); sabre runs a calendar-query only at `Depth: 1` and answers any other depth, or an href that is not a calendar, with a 207 without responses. Basic auth goes with the first request (the client never waits for a `401` challenge); HTTPS, 10 s timeout, 3 retries with backoff on timeouts and 5xx; `401`, `403` and `429` end the run without retry; the HTTP client keeps no cookies; outbound rules NFR-S7. Before each REPORT, one `PROPFIND` with `Depth: 0` on the href fails the refresh, keeping the last feed, unless `resourcetype` holds a calendar, the owner differs from the service user, and `current-user-privilege-set` lacks `{DAV:}write`; a 207 without responses counts as an empty calendar only after this check passed | ✔ | |
| FR-2 | Expand recurrences server-side (`expand`) | ✔ | local expansion with `recurring-ical-events` (MVP only if V-4 fails; guarded per Q-18) |
| FR-3 | Exclude `STATUS:CANCELLED`, timed events with `TRANSP:TRANSPARENT` (all-day events: Q-12), and events the owner has declined (`PARTSTAT=DECLINED` for configured owner e-mails; `NEEDS-ACTION` blocks, Q-19). Owner addresses are compared lower-cased as a whole, a pragmatic choice: RFC 5321 makes the local part case-sensitive | ✔ | |
| FR-4 | Reduce every event to `(start, end, tentative, allday)` immediately; discard all other fields | ✔ | |
| FR-5 | Window clip: `[today 00:00 local, today + window_days]` | ✔ | |
| FR-6 | Round to grid (default 15 min; start floored, end ceiled on local wall time in `tz`, using the UTC offset in force at each instant) and merge overlapping/adjacent intervals; `grid_minutes` must divide 1440 and every UTC-offset change of `tz` within 366 days after the run, so every rounded edge lands on the local grid; any other grid is a configuration error (AC-22) | ✔ | |
| FR-7 | Emit RFC 5545 ICS (with the RFC 7986 `REFRESH-INTERVAL`): `VEVENT` per merged interval, UTC, deterministic `UID`, `REFRESH-INTERVAL`/`X-PUBLISHED-TTL` = TTL, `X-WR-CALNAME`; no `METHOD` property. Configuration strings that reach the output (`summary`, the calendar name) contain no control characters (configuration error) and are TEXT-escaped by Milchglas per RFC 5545 section 3.3.11, never through icalendar's `vText`, which turns a literal `\N` into a newline | ✔ | |
| FR-8 | Write the feed atomically: a uniquely named temporary file in the feed's own directory, `fsync`, `os.replace`, then `fsync` of the directory; never via `tmpfs /tmp` (a rename across filesystems fails with `EXDEV`). On any failure keep the previous file and record the error. One run at a time: an exclusive lock file in `MILCHGLAS_VAR_DIR`; a second run exits non-zero without touching feed or state | ✔ | |
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
- NFR-P2 The busy pattern is minimised: window ≤ 33 days by default, 15-min grid, merged blocks (block count ≤ appointment count; isolated appointments stay individually visible).
- NFR-P3 Feed output contains exactly: `UID, DTSTAMP, DTSTART, DTEND, SUMMARY, TRANSP, STATUS` (+ optional `X-MICROSOFT-CDO-BUSYSTATUS`, off by default; only Exchange and Outlook document honouring it, both consumers use `TRANSP:OPAQUE`).
- NFR-P4 Errors are recorded as exception class, calendar index and HTTP status. Exception text from the parser or HTTP layers, calendar names, hrefs, request headers and response bodies never reach logs or state, at any log level. `MILCHGLAS_LOG_LEVEL=DEBUG` never enables `http.client` debug output.

### 7.2 Security
- NFR-S1 Feed access by capability URL: ≥ 256-bit random token, constant-time comparison, HTTPS only, `X-Robots-Tag: noindex`, `Referrer-Policy: no-referrer`, no directory listing. The token has 256 bits from a CSPRNG (`secrets.token_urlsafe(32)`) and is generated by `milchglas init`. `web` compares `hmac.compare_digest` over SHA-256 digests of bytes: the presented path segment is hashed as UTF-8 bytes and compared with the stored digest (D-14), so neither length, prefix nor a non-ASCII character changes the code path; `web` refuses to start on a malformed `token_sha256`. With one shared token (until FR-16), a leak at either consumer forces a rotation for both.
- NFR-S2 Secrets (`CALDAV_SECRET`, session secret) from environment or a `0600` file outside any document root; never in Git, images, config JSON or UI. The feed token is a secret: only its SHA-256 is stored (D-14).
- NFR-S3 The Nextcloud service user has read-only shares only and belongs to no group a calendar is shared with; every refresh checks each calendar's type, owner and privileges (FR-1); quota `0 B` (never `none`, which is unlimited); filesystem access is removed from its app password right after creation (Nextcloud always grants it then); the system address book is not exposed to it (or user enumeration is limited); its own calendars hold no events (its first login creates a `personal` calendar and an example contact). The app password is revocable in one click.
- NFR-S4 Process runs unprivileged; where possible read-only filesystem except the state directory; outbound connections only to the Nextcloud host. `web` holds no CalDAV credential (D-13). The egress limit is enforced by the systemd IP allow-list under Option A and is optional under Option B (Section 9).
- NFR-S5 Logs redact tokens. Access logs never contain the feed path: under Traefik drop `RequestPath` and `RequestLine` or disable access logs on the feed router (`observability.accesslogs=false`); Traefik cannot hash a field, and the platform replaces user access-log flags when its traffic analytics is on. Caddy may hash or replace `request>uri`. gunicorn runs without an access log. `web` logs one line per successful feed fetch with the client network (/24 for IPv4, /48 for IPv6), a user-agent class and the first 8 hex characters of `token_sha256`, never the token, so a third-party poller becomes visible before FR-16.
- NFR-S6 [LATER, with admin UI] scrypt password hashing from the standard library with N=2^17, r=8, p=1 and `maxmem` raised above `hashlib.scrypt`'s 32 MiB default (OWASP ranks Argon2id first, but its Python bindings are native code, NFR-O3); a time-boxed or exponential lockout instead of a fixed lock after 5 failures, which on the only admin account is a denial-of-service lever; HMAC-signed `HttpOnly; Secure; SameSite=Strict` cookie; a signed, session-bound double-submit CSRF token; optional CIDR allow-list.
- NFR-S7 Every CalDAV request goes to the origin (scheme, host, port) of `CALDAV_URL`, which must be `https`, with certificate verification on. A calendar href (`calendars[].href`) is the `<d:href>` of the PROPFIND answer, byte for byte, percent-encoding included; it is an absolute path without scheme, host or dot segments, and the dot-segment rule applies per decoded segment. A 3xx answer is a failure whose error names the status and the Location host. A refresh run has a total deadline (default 120 s) besides the 10 s socket timeout. The contract suite reaches its plain-HTTP server through an explicit test-only switch that production code never reads.

### 7.3 Reliability / fail-safety
- NFR-R1 Source failure never produces an empty or missing feed (D-7d). Zero enabled calendars is a configuration error (Q-16); objects that Nextcloud drops server-side are outside its reach (L5).
- NFR-R2 `/healthz` enables external alerting (uptime monitor → e-mail; AC-19).
- NFR-R3 [LATER] Fail-closed blockers after 48 h (FR-15).

### 7.4 Correctness
- NFR-C1 Golden tests: overlap merge, adjacency, grid rounding, DST spring/fall in `Europe/Berlin`, all-day, multi-day, tentative, cancelled, declined, RRULE + EXDATE + overridden instance, window clipping, UID determinism, RFC 5545 folding; output re-parses with `icalendar`.
  - A local time inside the spring gap takes the pre-gap offset (RFC 5545 section 3.3.5): 2026-03-29 02:30 Europe/Berlin is 01:30Z, so 02:30–03:30 yields no block and 02:30–04:00 yields 01:30Z–02:00Z.
  - Parser fixtures include a malformed `DTSTART`, a missing `DTEND` (RFC 5545 default length), an expanded instance that still holds `RRULE`, an entity bomb and an external entity naming a local file (Q-14); each yields exact blocks or a failed refresh with the last feed byte-identical and no file read.
  - The parser unfolds on bytes before UTF-8 decoding and accepts content lines over 75 octets (RFC 5545 section 3.1); the emitter folds strictly.
  - Each fixture records its provenance. sabre writes `calendar-data` as escaped XML text, never CDATA, so CDATA and raw-CRLF variants are synthetic robustness fixtures. Expanded answers carry CR as `&#13;`; unexpanded ones have LF-only lines, so the parser unfolds LF + space as well as CRLF + space. A `404` propstat is an error only for `calendar-data`; a `404` for another requested property is ignored.
  - A fuzz job (Atheris) exercises the parser on linux/amd64 only, because Atheris ships no macOS arm64 wheel and no sdist; the harness keeps the literal line `import atheris`, which OpenSSF Scorecard detects. If ClusterFuzzLite is adopted later, it runs batch fuzzing plus the continuous-builds task.
- NFR-C2 Contract tests against a sabre/dav-based server (Baïkal container) for PROPFIND, `calendar-query` + `expand` mechanics and (later) `free-busy-query`. Nextcloud sharee semantics (PRIVATE hidden, CONFIDENTIAL redacted, `_shared_by_` hrefs, objects the server cannot parse or iterate are absent from an otherwise normal 207, the 3500-instance limit) are pinned from AC-0.3 captures of the real server. The server stack is pinned: Nextcloud 35.0.x = sabre/dav 4.7.0 + sabre/vobject 4.5.6. The contract server is pinned by digest: the `ckulka/baikal` php8.2 variant (Baïkal 0.10.1, sabre/dav ~4.7.0; the default apache variant runs PHP 8.1, no longer supported; PHP 8.2 security support ends 2026-12-31). The suite records the Baïkal, sabre/dav and sabre/vobject versions (`composer show`); a vobject other than 4.5.6 is a recorded deviation. The expand-shape asserts of AC-0.3 also run on every contract answer.

### 7.5 Operability
- NFR-O1 One config file, one state file, one log stream; `python -m milchglas refresh` is idempotent and safe to run by hand. `python -m milchglas init` creates the UID salt and the feed token (the token is printed once, only its SHA-256 is stored, D-14); `rotate-token` replaces the token; `refresh` never generates a salt. `refresh --dry-run` prints counts and timestamps only; no command dumps raw source data. One run at a time (FR-8).
- NFR-O2 Runbook covers: rotate token (`rotate-token`, cadence Q-21), swap calendar, recover from stale/fail-closed, migrate host (copy state dir). It also covers:
  - a host migration changes DNS before the old host is released and rotates the token;
  - after each Nextcloud upgrade, search its `app: dav` entries for "for calendar data" (the parsing and the invalid-data exception) and for "max instances exceeded"; split daily series older than nine years (this assumes vobject's default of 3500 iterations, which AC-0.3 checks);
  - `owner_emails` lists every address the owner is invited under; an event that must not block is not marked confidential (D-3); an event that must block has no `CLASS` or exactly `PUBLIC` or `CONFIDENTIAL`, because Nextcloud hides any other value (L6); a list of the enabled calendars that third parties can write to, because their invitations block (Q-19);
  - the uptime monitor and its executed alert (AC-19); troubleshooting uses `refresh --dry-run` only;
  - a redeploy keeps the old `web` serving until the new one is healthy, because a non-200 answer makes mailbox.org wait 3600 s before its next fetch (OX `retryAfterErrorInterval`);
  - a CAA record with `accounturi` (RFC 8657) limits issuance to the operator's ACME account; MFA on the platform, the Git host and the DNS registrar is a deploy prerequisite; NTP is a prerequisite;
  - Option A installs only a release wheel verified with `gh attestation verify`, never a package by name (D-15);
  - the feed URL travels only from the server terminal to the consumer dialog, never through mail, chat or a browser tab; the feed host name names neither the person nor the purpose (Q-22);
  - the optional egress rule under Option B (Section 9).
- NFR-O3 Runtime dependencies pure Python only (`icalendar` and `tzdata`, plus `python-dateutil` through icalendar; `recurring-ical-events` and `x-wr-timezone` only with the FR-2 fallback) so Options A–C share one codebase. Once runtime dependencies enter `uv.lock`, CI fails on any wheel in the runtime closure that is not `py*-none-any` with `Root-Is-Purelib: true`.

---

## 8. Solution concept (host-independent core)

```
Nextcloud ──read-only CalDAV (svc-milchglas)──► Milchglas core
                                                   fetch → expand → filter → reduce → clip → round → merge → emit
                                                   └─► busy.ics (atomic write; keep last good on error)
                                                              │
                                        HTTPS  /f/<token>.ics │  (WSGI route; Option D: static file)
                                   ┌──────────────────────────┴──────────────────────────┐
                                   ▼                                                     ▼
                     mailbox.org: subscribed iCal feed                     meetergo: ICS conflict calendar
                     "Blocker Privat" blocks                               (bookings still written to mailbox.org via CalDAV)
```

**Core pipeline (pure functions, unit-tested):**
```
intervals = fetch_all(enabled_calendars, window)            # FR-1..FR-4
intervals = clip(intervals, window)                          # FR-5
intervals = round_to_grid(intervals, grid_minutes, tz)       # FR-6
intervals = merge(sorted(intervals))                         # FR-6  (set union)
ics       = emit(intervals, summary, uid_salt, ttl_seconds, version, now,
                 previous_stamps)        # FR-7
atomic_replace("busy.ics", ics) if ok else keep_previous()   # FR-8
```

**ICS skeleton:**
```
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Milchglas//<version>//DE
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

**Config (`config.json`, non-secret):** `tz`, `window_days` (33), `grid_minutes` (15), `summary`, `ttl_seconds` (900), `allday_mode`, `tentative_mode`, `owner_emails`, `calendars[] {href, name, enabled}`, `token_sha256` (hex SHA-256 of the feed token; the token itself is never stored on the server; MVP: single), `uid_salt`. Validated on every refresh (AC-22).
**Environment:** `CALDAV_URL`, `CALDAV_USER`, `CALDAV_SECRET`, `MILCHGLAS_VAR_DIR`, `MILCHGLAS_LOG_LEVEL`.

**Repository layout (proposed):**
```
milchglas/
├── CLAUDE.md  README.md  pyproject.toml
├── src/milchglas/{__main__.py, config.py, state.py, refresh.py}
├── src/milchglas/sources/{caldav.py, parse.py}
├── src/milchglas/core/{model.py, reduce.py, emit.py}
├── src/milchglas/web/{app.py, feed.py}          # WSGI; used by A, B (gunicorn) and C (Passenger)
├── tests/{unit, fixtures, contract}
├── deploy/{vps-systemd, docker-paas, shared-hosting-python, shared-hosting-php}   # one folder per Option
└── docs/{adr, runbook.md, consumers.md}
```

---

## 9. Deployment options

All four options share Sections 6–8 unless stated. Differences are in scheduling, serving, secrets, maintenance and security posture.

### Option A — Script as cron job or daemon on a Linux VPS
- **Shape:** Python package in a venv; a `systemd` refresh service + timer (every 15 min) or a `--loop` daemon, and a service running the WSGI app behind Caddy (automatic TLS) or the existing proxy; state in `/srv/milchglas`, owned by the static system user `milchglas`.
- **Prerequisites:** either a VPS where ports 80/443 are free (Caddy obtains the certificate itself), or a route in an existing proxy. On a self-hosted PaaS host where Traefik (or a similar edge proxy) already owns 80/443, Option A there means either a file-provider route to a local port (Traefik terminates TLS and owns the certificate; the local service speaks plain HTTP on localhost) or a *second* small VPS (≈ €6–10/month, measured 2026-10-21).
- **Scheduling:** native cron/systemd timer — the simplest and most transparent mechanism of all options.
- **Secrets:** `EnvironmentFile=/etc/milchglas/env` (`0600`, root-owned), loaded by the refresh unit only (D-13). Hardening: static `User=milchglas` (sysusers.d), `ProtectSystem=strict`, `ReadWritePaths=/srv/milchglas` on the refresh unit, `PrivateTmp=yes`, `NoNewPrivileges=yes`; egress `IPAddressDeny=any` plus `IPAddressAllow=` for the CalDAV host's addresses, the resolver and localhost (an allow-list alone blocks nothing; entries are IP prefixes, not names; the filter needs eBPF cgroup support); `LimitCORE=0`, `CapabilityBoundingSet=`, `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`, `SystemCallFilter=@system-service`. A provider address change fails the refresh visibly (D-7d). A unit-file test fails when a directive is missing; `systemd-analyze security` stays below a stated score.
- **Maintenance:** SSH + edit `config.json`; `systemctl start milchglas-refresh` to force a run; token rotation = `rotate-token` and update the consumers; upgrades install only a release wheel verified with `gh attestation verify` (D-15).
- **Security posture:** strongest of all options (systemd sandbox, kernel-level egress allow-list, no container daemon).
- **Effort:** 1 evening if a VPS with free ports exists; +1 hour for Caddy/TLS.
- **Pros:** minimal moving parts; best hardening; no Docker.  **Cons:** awkward when the PaaS host already owns ports 80/443; a second VPS adds cost and upkeep; no Git-push deploys.

### Option B — Docker container(s) on a self-hosted PaaS (recommended for now)
- **Shape:** one image (`python:3.12-slim`, non-root UID, `read_only` FS, `tmpfs /tmp`, volume for state). Compose services: `web` (gunicorn serving `/f/<token>.ics` and `/healthz`) and `refresher` (`python -m milchglas refresh --loop --interval 900`). Traefik (or the PaaS's built-in proxy) provides TLS on an operator-chosen subdomain, e.g. `k7q2.example.org`. Python 3.12 receives security fixes only and reaches end of life around 2028-10 (PEP 693); the image moves to a newer minor before then.
  - Hardening, both services: non-root `user`, `read_only: true`, `tmpfs /tmp`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, `ulimits: core: 0`, memory and pids limits, no Docker socket; the volume mounted read-only in `web`; `config.json` read-only in both; only `web` publishes a port. The Dockerfile pins `python:3.12-slim` by digest, installs only with `uv sync --frozen --no-dev`, and creates and chowns the state directory (a non-root process can write an empty named volume only then). Dependabot watches the image with an ignore rule that holds the 3.12 minor. Whether the platform keeps `read_only`, `cap_drop`, `security_opt` and `tmpfs` is unverified until `docker inspect` checks it after deployment (AC-13).
  - gunicorn runs with `--no-control-socket` (since 25.1.0 it opens a control socket under `$XDG_RUNTIME_DIR` or `$HOME/.gunicorn` by default, which fails on a read-only root and is only logged), `--worker-tmp-dir /tmp`, no access log, and a worker timeout.
- **Prerequisites:** DNS record for the chosen subdomain; the PaaS app created from the Git repo.
- **Scheduling:** in-container loop (or `supercronic`); `web` never refreshes and holds no `CALDAV_*` (D-13).
- **Secrets:** the PaaS's environment variables: encrypted in the platform database, but written in plaintext to a server-side `.env` at each deployment and visible in the container environment; never in the image. Only `refresher` receives `CALDAV_*`; whether the platform injects every variable into every Compose service is unverified, and if it does, `web` refuses to start until the Compose file scopes the variables per service.
- **Maintenance:** a push to the protected `main` branch → redeploy (the platform builds the image itself, so a release tag would add no provenance); a redeploy keeps the old `web` serving until the new one is healthy (NFR-O2). `config.json` on the volume is edited through the platform's file-mount editor (the slim image ships no editor for the terminal); the config directory is mounted, not the single file, because a single-file bind mount keeps the original inode, so an edit that writes a new file and renames it can stay invisible to the container (Docker behaviour, not re-verified). `/healthz` is wired to an HTTP uptime monitor (AC-19).
- **Security posture:** good; egress restriction is optional and documented in the runbook (a host `DOCKER-USER` rule allowing only the CalDAV host; Docker applies no per-container egress filter by default, and the rule lives on the host outside the repository and breaks on a provider address change); the PaaS and its edge proxy are already exposed anyway.
- **Effort:** 1 evening for MVP; matches a common self-hosting platform and mental model.
- **Pros:** fits a Docker/Git-based workflow already in place; Git-based deploys; logs and health in one place; stateless image makes migration a volume copy.  **Cons:** long-term availability of the current host is not guaranteed; Docker layer; per-app egress control is manual.

### Option C — Python script on shared web hosting (incl. website/UI)
- **Shape:** WSGI app under Phusion Passenger on a subdomain (`passenger_wsgi.py`, app root **outside** `httpdocs`). The same app serves the feed route *and* the maintenance website (Section 12, FR-17/18) — on this class of shared hosting this is not optional, because there is no other way to trigger Python: no CLI, no Python cron [FACT].
- **Prerequisites:** a hosting tier that includes Python support [VERIFY V-6]; pure-Python dependencies vendored by hand (no `pip`); secrets in a `0600` env file in the app root outside `httpdocs`, parsed by `passenger_wsgi.py` with a stdlib parser, because Passenger has no `.env` loader and the panel's Python module has no environment field [VERIFY V-6].
- **Scheduling:** *lazy refresh* on feed request when cache age > TTL, plus a panel scheduled task of the type "Fetch a URL" every 15 min against the feed URL (no `curl` needed in the chrooted shell). It keeps the cache warm; it does not keep the Passenger process alive (Passenger's default idle time is 300 s), so expect a cold start per refresh [VERIFY V-6 reads the host's idle time].
- **Secrets:** the `0600` env file on a shared filesystem — weaker than A/B by nature.
- **Maintenance:** the in-app admin UI (auth per NFR-S6) is the primary maintenance channel; code updates via SFTP/Git; remember the *disable → enable* quirk after settings changes [FACT, 4.4].
- **Security posture:** shared hosting; no egress control, limited logs; mitigated by D-2 (read-only service user, revocable app password).
- **Effort:** 2–3 evenings (vendoring, Passenger quirks, admin UI becomes MVP-mandatory here).
- **Pros:** runs on web hosting many operators already have; needs no VPS; no Docker.  **Cons:** tariff dependency; hand vendoring; Passenger sandbox; admin UI is forced into MVP scope; shared filesystem for the secret.

### Option D — PHP application on shared web hosting
- **Shape:** PHP 8.x CLI script run by the hosting control panel's cron every 15 min (`php -f /…/milchglas/refresh.php`), writing `<token>.ics` into a subdomain docroot; served as a static file by Apache/nginx; optional admin page protected by directory protection (`.htaccess`) — Passenger is not involved, so directory protection works normally.
- **Prerequisites:** any shared-hosting tariff with PHP + cron + SSH included [FACT: PHP CLI via SSH; scheduled tasks can run a PHP script]; Composer via SSH (`php composer.phar require sabre/vobject:4.5.6`, the version the Nextcloud server pins, for byte parity) for parsing and recurrence iteration [Composer availability: VERIFY V-6; fallback: vendor sabre/vobject offline], or rely on CalDAV server-side `expand` with a minimal hand-written parser.
- **Scheduling:** real cron — as clean as Option A.
- **Secrets:** `config.php` outside the docroot, `0600`; same shared-filesystem caveat as C.
- **Maintenance:** SFTP/Git + `.htaccess`-protected status page; token rotation = rename file.
- **Security posture:** as C, but a smaller runtime surface (no long-running app server, no custom auth code if `.htaccess` is used).
- **Effort:** 1–2 evenings; a *separate codebase* from A/B/C (port of `reduce`/`emit` with the same golden test fixtures).
- **Pros:** the natural fit for shared hosting — cron works, no tariff upgrade, no vendoring, no Passenger.  **Cons:** second language; the recurrence iterator library must be trusted (it is the same library the CalDAV server uses server-side — a reasonable trust anchor); divergence risk from the Python core.

### 9.1 Comparison

| Criterion | A · VPS script | B · PaaS Docker | C · shared-hosting Python | D · shared-hosting PHP |
|---|---|---|---|---|
| Scheduling | native timer ★ | in-container loop | lazy + panel URL task | native cron ★ |
| Secrets at rest | root-owned env file, sandboxed ★ | PaaS env (encrypted in the platform DB, plaintext `.env` on the server) | shared FS `.env` | shared FS config |
| Egress control | systemd IP allow-list with `IPAddressDeny=any` ★ | manual Docker rules | none (assumed; V-6) | none (assumed; V-6) |
| Maintenance channel | SSH | Git push + file-mount editor | in-app UI (mandatory) | SFTP + `.htaccess` page |
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
- **AC-0.1** A hand-written test feed with the exact header the code ships (the Section 8 skeleton, without `METHOD`; D-8), two UTC timed events and one `VALUE=DATE` all-day event, each with `DTSTAMP`, on a public HTTPS URL, is subscribed in mailbox.org and appears under *Meine Kalender*. The record in `docs/consumers.md` states the propagation time after an edit, whether PT15M is honoured or the 7-day OX default applies, and how the all-day block is shown. *(V-1)*
- **AC-0.2** The same feed connected in meetergo as an ICS calendar blocks a timed test slot and the all-day test day in the booking page, on the meeting type actually used. *(V-5)*
- **AC-0.3** `svc-milchglas` exists; `PROPFIND` with its app password lists the shared calendars; a `calendar-query` with `expand` returns instances of a recurring test event including an overridden instance and an excluded date. The record shows each NFR-S3 setting; a WebDAV file `PUT` with the app password fails; a PROPFIND on the service user's address-book home lists no system address book; the service user is no calendar delegate (proxy) of the owner (OR3); the PROPFIND records each shared calendar's `calendar-timezone` (L11). The REPORT runs with redirects disabled and its status is recorded (NFR-S7), as are the instance count and the response size for the window. The captured `expand` answer is asserted: no `RRULE`, `RDATE`, `EXDATE` or `VTIMEZONE` in any instance; every instance of a recurring object carries a `RECURRENCE-ID` distinct within its `UID`, single events carry none, and overrides keep their own properties; all-day instances stay `VALUE=DATE` and every timed DATE-TIME is UTC. Captured on the real server: `EXDATE;VALUE=DATE` on a timed series; a series with two `RDATE` lines; a daily series started more than 3500 days before the window (expected absent: the silent drop of L5); an object holding only an unmoved overridden instance and no master, and one holding only a moved one; an RDATE-only series that starts before the window with two `RDATE`s inside it; an RRULE series with one `RDATE` (each outcome pinned as observed, L5); a `P1D` event across 2026-03-29 and one across 2026-10-25 (Q-20); a cancelled override (expected present with `STATUS:CANCELLED`); a declined invitation written by the owner's real client; a CONFIDENTIAL event as the sharee receives it (D-3); one all-day event per client the operator uses, with its `TRANSP` value (Q-12); one event with floating times (L11). *(V-2, V-4)*
- **AC-0.4** Every meetergo meeting type's booking window (a weekday-based window converted to calendar days) is confirmed ≤ `window_days` - 3, or `window_days` is raised accordingly. *(Q-2)*

### 10.2 MVP functional
- **AC-1** Given three enabled calendars with overlapping events, when refresh runs, then the feed contains merged intervals only, and no interval overlaps or touches another of the same kind (timed or all-day, Q-9).
- **AC-2** Given a weekly recurring event with one excluded date and one moved instance, the feed contains blocks for exactly the real occurrences within the window.
- **AC-3** Given events on the DST transition days of `Europe/Berlin`, local start/end times in the feed (converted from UTC) match the source; a timed event with `DURATION:P1D` across each transition ends at the same local time the next day (Q-20).
- **AC-4** Given a cancelled event, a transparent timed event and an event the owner declined (all `CLASS:PUBLIC`), none produces a block; a `CLASS:CONFIDENTIAL` event as the read-only sharee receives it (`SUMMARY` "Busy", localised, such as "Beschäftigt" in German; no `STATUS`, `TRANSP` or `ATTENDEE`) produces one (D-3).
- **AC-5** Given an all-day event, including one with `TRANSP:TRANSPARENT` (a common client default), the feed contains a `DATE`-valued all-day block (default mode; Q-12).
- **AC-6** Given an unchanged source, two consecutive refreshes produce byte-identical feeds (same `UID`s, same `DTSTAMP`), and mailbox.org shows each block once after two refresh cycles, without deleting and re-adding blocks (OX matches feed events by UID). *(V-7)*
- **AC-7** Given the Nextcloud host is unreachable, the previous feed file remains byte-identical and `/healthz` turns 503 after 60 min. The temporary file and the feed share a directory; an injected full disk (`ENOSPC`) keeps the previous feed byte-identical; a second concurrent run exits non-zero and leaves one complete feed (FR-8).
- **AC-8** The feed body contains no property other than `UID, DTSTAMP, DTSTART, DTEND, SUMMARY, TRANSP, STATUS` (and the optional Microsoft busy hint); a test greps the output and every log line for any fixture title and finds none. A fixture with malformed `SUMMARY`, `DESCRIPTION` and `LOCATION` lines carrying a fixture title is refreshed at `DEBUG` against a fixture server: the title, the `Authorization` header, the secret and its base64 form appear in no stdout or stderr line, no state field and no HTTP response; an error on a calendar with a fixture name leaves no line with that name or href (NFR-P4).
- **AC-9** Requests cover methods (`GET`, `HEAD`, `OPTIONS`, `POST`) × right or wrong token × conditional headers (`If-None-Match`, `Range`) × path variants (`/f/../state`, `%2e%2e%2f`, `%00`, `//f/`, `.ICS`, a trailing slash, `;` parameters, double encoding, a non-ASCII token such as `/f/ä.ics`): every wrong-token response is byte-identical to the unknown-path response apart from `Date`. The correct token returns `200 text/calendar; charset=utf-8` with `ETag`, `X-Robots-Tag`, `Referrer-Policy`, `X-Content-Type-Options: nosniff` and `Cache-Control: private, max-age=0`; the 404 carries the last two. No versioned `Server` header. Wrong-token and unknown-path requests share a timing class: the medians of 1000 of each, measured locally, differ by less than a stated bound.
- **AC-10** `config.json` edit (`enabled: false` on one calendar) + refresh removes that calendar's blocks; no restart needed. The edit is made the way the operator makes it (the platform's file-mount editor, or an editor that replaces the file), and the next refresh sees it.
- **AC-11** meetergo does not offer a slot that overlaps a private block; mailbox.org shows the block in the subscribed calendar within 30 minutes of the private change (one 15-minute refresh interval plus one `REFRESH-INTERVAL` of `PT15M`).
- **AC-20** Token rotation needs no restart: after `rotate-token`, within one refresh interval the old token returns the identical 404 and the new one 200; under Option A no file is named after any token (D-14).
- **AC-22** Configuration is validated on every refresh. Unknown keys; `window_days` outside 1..90; a `grid_minutes` that does not divide 1440 and every UTC-offset change of `tz` within 366 days after the run (FR-6); an unknown `tz`; zero enabled calendars (Q-16); a missing salt (Q-13); a plaintext `token` key (D-14); control characters in output strings (FR-7); a non-`https` `CALDAV_URL` or an href with scheme, host or a dot segment after decoding (NFR-S7): each fails the refresh before any request and keeps the last feed. A changed configuration logs the names of the changed keys, never values. Rounding lays the grid on local wall time with the UTC offset in force at each instant and never rebuilds a local datetime from components, which loses `fold`; a start only moves earlier and an end only later. 7, 25 and 50 are rejected; 15, 30 and 60 pass for Europe/Berlin, where 45, 90 and 120 are rejected; 45, 90 and 120 pass for Asia/Kolkata; 60 is rejected for Australia/Lord_Howe. 60 with Asia/Kolkata (+05:30) floors to local full hours; 2026-10-25 02:07 with `fold=1` rounds to 01:00Z.

### 10.3 MVP non-functional
- **AC-12** `ruff`, `mypy --strict`, `pytest` green in CI; runtime dependencies are pure Python.
- **AC-13** Container/process runs unprivileged; secret is not present in image layers, Git history or config file (CI secret scan). CI builds the image and scans its layers and its image configuration (`--image-config-scanners secret`) for secrets; the scanner's action is pinned by commit SHA (its release actions were compromised on 2026-03-19); a planted canary in a format outside the scanner's built-in allow rules must fail the job. A CI check over the Compose file and Dockerfile fails on a missing hardening key (Section 9, Option B), a `FROM` without digest or any `pip install`. After deployment `docker inspect` shows `ReadonlyRootfs`, `CapDrop` and `SecurityOpt` on both services; that the platform keeps these keys is an assumption until then. gunicorn starts without warnings in the read-only container.
- **AC-14** Runbook documents token rotation, calendar swap, stale recovery and host migration; each procedure has been executed once. The execution record has one checked line per NFR-O2 item, and `docs/consumers.md` holds one field per AC-0.1 and AC-0.2 observation; an empty field fails the review.
- **AC-19** An external monitor polls `/healthz` at least every 5 minutes; a 503 sends an e-mail to the operator; during deployment the refresher is made to fail (wrong password) and the alert is observed after the 60-minute threshold.
- **AC-21** After deployment one fetch with a canary token leaves zero hits in proxy, platform and app logs; the canary path returns the identical 404; the plain-HTTP router answers 404 for `/f/*`, never a redirect. A loop that fetches the feed every second for the whole redeploy sees no non-200 answer.

### 10.4 Later features (when pulled from backlog)
- **AC-15** (FR-15) After `stale_max_age`, the feed contains one all-day blocker per day in the window and `/healthz` reports fail-closed state.
- **AC-16** (FR-16) Rotating the `meetergo` token invalidates only meetergo's URL after the grace period; mailbox.org keeps working.
- **AC-17** (FR-17/18) Admin dashboard HTML contains no `DTSTART`/interval data; login lockout after 5 failures; a login after the lock window expires succeeds; CSRF rejected, including a CSRF token from another session.
- **AC-18** (FR-19) With `free-busy-query`, a packet capture / debug log of the CalDAV exchange contains no `SUMMARY` lines.

---

## 11. Verification plan for assumptions

| ID | Assumption | Test | If false |
|---|---|---|---|
| V-1 | mailbox.org subscribes external ICS via *Von URL (iCal) importieren* and refreshes periodically | AC-0.1 | mailbox.org half unreachable via feed → FR-20 CalDAV push variant (Milchglas writes blocker VEVENTs into a dedicated mailbox.org calendar) |
| V-2 | Shared calendars are visible/readable to `svc-milchglas` via CalDAV | AC-0.3 | Check share flags, group app restrictions |
| V-3 | Nextcloud supports `free-busy-query` REPORT [LATER] | `curl -X REPORT` + PROPFIND `supported-report-set` | Stay on `calendar-query`; content transits memory only |
| V-4 | `calendar-query` + `expand` applies EXDATE and overridden instances correctly and drops no instance in the window | AC-0.3 vs `recurring-ical-events` on the same fixture, including the orphan, RDATE-only and RRULE + RDATE cases of L5 | Request without server filtering (a `VEVENT` comp-filter only, no `time-range`, no `expand`; the response size measured against Q-15 first) and expand locally: the FR-2 fallback becomes MVP, guarded per Q-18 |
| V-5 | meetergo treats feed events as blocking without auth | AC-0.2 | Check per-calendar availability settings in meetergo |
| V-6 | Shared-hosting tariff with Python support in the control panel; an app-parsed `0600` env file reaches the app under Passenger | control panel → Dev Tools; record the provider's identity, the Python versions offered (3.12 or a lowered `requires-python`), which env path reaches the app (own env-file parser or `SetEnv`), Passenger's idle time, whether a protected path returns 401 for a PHP app and for a Passenger app, the filesystem type under the app root (atomic `os.replace`), Composer over SSH, and an outbound connection test from PHP | Option C infeasible → D or B; Option C stays infeasible while any recorded field is empty |
| V-7 | Deterministic UIDs keep OX from deleting and re-adding every block on each refresh (OX diffs by UID; tombstones are capped at 2500 per account) | AC-6 | Add `SEQUENCE`, adjust UID scheme |
| V-8 | On the self-hosted PaaS host, Traefik routes a subdomain to the container with TLS without manual Caddy | Deploy hello-world first | Fall back to Option A routing |
| V-9 | Consumers keep their last copy while the feed is unreachable | With the feed answering 404, 503 and a timeout: meetergo still blocks the test slot and refuses a booking; mailbox.org keeps the blocks | An availability target for `web` (new NFR-R) and a review of FR-15 |

---

## 12. Concept ideas & backlog (not MVP)

| Idea | Value | Cost | Trigger to pull forward |
|---|---|---|---|
| **Free-busy-query acquisition** (FR-19) | Content never transits Milchglas — strongest privacy statement; but the free-busy path cannot exclude owner-declined events, loses `TRANSP`/`STATUS` on confidential events and never sees private ones, so FR-3 parity is impossible | 1 evening + V-3 | After MVP is stable |
| **Fail-closed blockers** (FR-15) | Outage cannot become double bookings | 1 hour | First time the feed was stale > 1 day |
| **Per-consumer tokens with rotation grace** (FR-16) | Attributable leaks, independent revocation | 2 hours | Third consumer or first suspected leak |
| **Admin UI** (FR-17/18) | Maintenance without SSH | 1–2 evenings | Third manual `config.json` edit, or Option C |
| **PROPFIND discovery + `missing` flag** | See withdrawn shares immediately | 1 hour | With admin UI |
| **All-day / tentative modes** (FR-13/14) | Birthdays should not block bookings | 1 hour | First lost booking due to an all-day event [OPEN Q-1] |
| **Per-source settings** | e.g. a vacation calendar's all-day events = busy, a family calendar's all-day events = ignore | 1 hour | With modes |
| **Mobile token** (ICSx5 / iOS subscription) | Busy overlay on phone if mailbox.org does not sync feed calendars over CalDAV (the OX default would; test on one phone, Q-5) | 30 min | If wanted [OPEN Q-5] |
| **Reverse WebCal** (Nextcloud subscribes mailbox.org `?ical=true`) | One private view of all standard-visibility appointments (private-classified OX appointments show times only) — zero code; Nextcloud refreshes a subscription per its `REFRESH-INTERVAL`, else daily per the admin manual (the user manual says weekly) | 5 min | Anytime |
| **CalDAV push into mailbox.org** (FR-20) | Independence from OX feed cache; works if V-1 fails | 1 evening | V-1 fails or cache interval unacceptable |
| **Baïkal contract tests in CI**, then an official Nextcloud container in the contract suite | Protects recurrence handling on upgrades; the Nextcloud container makes the sharee semantics of NFR-C2 reproducible instead of captured | 2 hours, plus the Nextcloud image and share setup | Before first Nextcloud major upgrade |
| **Option A unit files** | Post-migration landing spot | 30 min | Before moving off a PaaS host |
| **Rewrite evaluation** (D-12) | Single static binary, smaller image and memory footprint; possibly one codebase for shared hosting instead of the Option D port | Open until evaluated; a rewrite reuses the golden fixtures (NFR-C1) as its parity check | MVP works and is deployed |

---

## 13. Open questions

| ID | Question | Default until answered |
|---|---|---|
| Q-1 | All-day events: block bookings (`busy`) or ignore? Should a dedicated out-of-office calendar be the only all-day source? | `busy` |
| Q-2 | meetergo booking window per meeting type: at most `window_days` - 3 calendar days? | `window_days` 33 |
| Q-3 | Feed summary text and whether tentative appointments appear as a distinct "Vorläufig" | `Blocker Privat`, tentative = busy |
| Q-4 | Fail-closed threshold (when the feed is stale, how long until booking is blocked?) | 48 h (backlog). meetergo keeps its last loaded busy times on a failed update and blocks the host without data, so fail-closed covers only the stale-data case |
| Q-5 | Mobile subscription wanted in v1? | no |
| Q-6 | Hostname (operator-chosen subdomain?) and DNS location | an operator-chosen subdomain, e.g. `k7q2.example.org` |
| Q-7 | Runbook / consumer docs in German? | German |
| Q-8 | Deployment decision D-9: B now, A later? Or D because shared hosting must host it? | B |
| Q-9 | A timed busy block overlaps an all-day busy block: merge them into one, or keep both? | Keep both; the no-overlap, no-touch rule of AC-1 applies per kind |
| Q-10 | Tentative flag of a merged block when tentative and confirmed events overlap | Tentative only if every merged interval is tentative (the MVP emits tentative as plain busy, FR-14) |
| Q-11 | Does the owner's own `PARTSTAT=TENTATIVE` mark a block as tentative? | Yes, same as `STATUS:TENTATIVE` |
| Q-12 | Does `TRANSP` decide whether an all-day event blocks? | No: for all-day events `TRANSP` is ignored and `allday_mode` (Q-1) decides, because most clients default all-day events to free (`TRANSPARENT`); timed events keep the FR-3 rule. The all-day default of the operator's own clients is an assumption until one all-day event per client is captured |
| Q-13 | Source and lifetime of the UID salt (ICS skeleton, Section 8) | A non-secret value (`uid_salt`) generated once by `milchglas init` and stored in `config.json`; `refresh` never generates one and fails without it; changing it changes every UID, so consumers delete and re-add every block once |
| Q-14 | One unparsable calendar object among valid ones: skip it or fail the refresh? | Fail the refresh and keep the last good feed (D-7d); skipping it would silently create a free slot. An object is unparsable when the parser reports any error for it, including errors collected in lenient mode (a non-empty `errors` list), or when an expanded answer still carries `RRULE` or `RDATE` while local expansion is off. A multistatus body with a DOCTYPE is rejected before parsing (an expat handler that raises on a DOCTYPE or entity declaration; stdlib only, NFR-O3). Objects that Nextcloud drops server-side never reach Milchglas (L5) |
| Q-15 | Retry backoff steps for FR-1 and the maximum response size | 1 s, 2 s, 4 s between the three retries; 16 MiB. Only timeouts and 5xx are retried (FR-1): from version 32 on, Nextcloud answers a failed login with `401` at once and with `429` after more than 10 failures from one subnet within both 12 hours and 30 minutes (older versions delayed each failure by up to 25 s), so retrying turns a wrong password into a lockout |
| Q-16 | Every enabled calendar answers successfully but holds no events: publish an empty feed? | Yes: publish a valid feed without events and record the success. Zero calendars with `enabled: true` is a configuration error (the refresh fails, the last feed stays). Per calendar, the returned object count is recorded in state; a calendar whose count drops from non-zero to zero, and a feed that drops from non-empty to zero blocks, record a warning (counts only) in state and log. Any failure (transport error, non-success status, unparsable body, unknown calendar) keeps the previous feed and never yields an empty one (D-7d, NFR-R1) |
| Q-17 | Response headers beyond NFR-S1: `X-Content-Type-Options: nosniff` and `Cache-Control: private, max-age=0` | Send both |
| Q-18 | What triggers local recurrence expansion (the FR-2 fallback)? | An explicit configuration setting, off by default; no automatic switch on a server error. Before it can be enabled, local expansion has a per-run time budget and a maximum instance count per object, and treats sub-hourly `FREQ` (`SECONDLY`, `MINUTELY`) as unparsable. Floating times: local expansion reads them in `tz`, sabre in the calendar's `calendar-timezone`, else UTC, so both paths agree only where these match |
| Q-19 | Does an event whose owner attendee has `PARTSTAT=NEEDS-ACTION` (or no `PARTSTAT`, which RFC 5545 defaults to NEEDS-ACTION) block? | Yes (busy); a mode switch is LATER, like FR-13 and FR-14. A block too many costs a slot, a block too few a double booking |
| Q-20 | Expanded instances of a `DURATION`-based event keep `DURATION` with a UTC `DTSTART` (sabre/vobject 4.5.6). How is the end computed? | Day and week components are added as a nominal duration in `tz`, time components as exact time (RFC 5545 section 3.3.6): a `P1D` instance starting 2026-10-24 07:00Z ends 2026-10-25 08:00Z. An event created in a zone with other DST dates can be off by one hour. This rule covers UTC and floating starts; a start with a resolvable `TZID` counts its days in that zone (RFC 5545 section 3.3.6) |
| Q-21 | Token rotation cadence? | Yearly and after any provider breach notice; until FR-16 both consumers are re-subscribed together |
| Q-22 | Should the busy pattern be minimised beyond NFR-P2 (a coarser default grid, merging blocks separated by less than a gap, per-source all-day handling)? | No: the NFR-P2 defaults stay until real data shows the trade-off, because merging lowers the block count only for overlapping or touching appointments. The runbook advises a feed host name that names neither the person nor the purpose (Q-6) |

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
