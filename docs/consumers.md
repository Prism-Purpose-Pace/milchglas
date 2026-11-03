# Consumer setup: mailbox.org and meetergo

This page describes how the two consumers read the Milchglas feed (spec OR10, D-4) and
records which gates passed (AC-0.1, AC-0.2, AC-0.4; MAN-1). Host names, feed URLs, tokens,
account names, calendar names and details of an operator's account do not belong here; the
maintainer keeps the detailed record privately.

## Setup steps

Each step says what to do, where, why and how. Menu labels are quoted as the German web
interfaces show them (*German UI*). A German version of this page is
[consumers.de.md](consumers.de.md); where the two differ, this English page applies (D-10).

### Step 1: Create the feed URL

- **What:** create the token and with it the feed URL `https://<host>/f/<token>.ics`.
- **Where:** on your own machine, never in the platform's web terminal, which is a browser
  tab (spec NFR-O1, threat model T-62).
- **Why:** the URL is the secret. `init` or `rotate-token` prints the token once; the server
  holds only its SHA-256 (spec D-14). Whoever knows the URL sees only anonymous blocks.
- **How:** run `init` (or `rotate-token` for a new URL). In each consumer's dialog type
  `https://<host>/f/`, paste the printed token and append `.ics`. Never send the URL by
  mail, chat or link shortener and never open it in a browser tab: link previews, mail
  scanners, history and extensions store it (threat model T-35). After a rotation, enter
  the new URL in both consumers.

### Step 2: Subscribe in mailbox.org

- **What:** subscribe the feed once as an iCal feed calendar.
- **Where:** mailbox.org web client, calendar.
- **Why:** mailbox.org then shows the busy time as anonymous blocks. It honours the feed's
  `REFRESH-INTERVAL` (set by `ttl_seconds`), not the 7-day Open-Xchange default.
- **How:**
  1. Arrow next to *Neuer Termin* → *Von URL (iCal) importieren* → *iCal-Feed abonnieren*
     (German UI).
  2. Paste the feed URL and confirm.
  3. The calendar appears under *Meine Kalender* (German UI). It is read-only.

### Step 3: Connect the ICS calendar in meetergo

- **What:** connect the feed once per profile, not per meeting type; it applies to every
  meeting type of that profile (meetergo help "Connecting ICS calendars", as of 2026-09-16).
- **Where:** meetergo profile, entry *Proton/ICS Calendar*.
- **Why:** meetergo then stops offering busy time. It requires a publicly reachable HTTPS
  URL without authentication. Every event in the ICS calendar blocks, all-day ones
  included; only events marked free and cancelled ones do not (meetergo help, as of
  2026-07-28). Milchglas writes every block as `TRANSP:OPAQUE` and `STATUS:CONFIRMED`.
- **How:** add the ICS calendar with the feed URL and save.

### Step 4: Limit the meetergo booking windows

- **What:** no meeting type may be bookable more than `window_days` - 3 calendar days ahead
  (spec Q-2).
- **Where:** meetergo, settings of each meeting type.
- **Why:** blocks exist only up to today + `window_days` (spec L2); days beyond would show
  as free.
- **How:** check each meeting type's booking window. A window counted in weekdays is longer
  in calendar days; an unlimited window is not allowed. A new meeting type starts with 30
  calendar days. Before extending a window, raise `window_days` in `config.json`.

## Gate results (MAN-1)

Checked with a synthetic test feed that carries the shipped header (no `METHOD`,
`REFRESH-INTERVAL` and `X-PUBLISHED-TTL` `PT15M`), with two UTC blocks and one all-day block
(`VALUE=DATE`). A second version moved one block, with a new UID as in a real refresh.

MAN-2, the fallback for a consumer that rejects the `METHOD`-less header or the all-day
block, was not needed: both consumers accepted both.

### AC-0.1 mailbox.org: passed

| Observation | Result |
|---|---|
| Appears under *Meine Kalender* | yes |
| All blocks visible | yes, with `TRANSP:OPAQUE` and status busy |
| How the all-day block shows | as an all-day event, status busy |
| Header without `METHOD` accepted | yes |
| Change visible | within the 30 minutes of AC-11 |
| `PT15M` honoured | yes, not the 7-day default (V-1 passed) |
| UID change | old block removed, new block present, no duplicate |

### AC-0.2 meetergo: passed

| Observation | Result |
|---|---|
| Timed block not bookable | yes |
| All-day block: day without a bookable slot | yes |
| Unauthenticated feed treated as busy | yes (V-5 passed) |
| Header without `METHOD` and `VALUE=DATE` accepted | yes |
| Change effective | within the 30 minutes of AC-11 |
| Scope | profile-wide, every meeting type |

### AC-0.4 meetergo booking windows: passed

| Observation | Result |
|---|---|
| Every booking window ≤ `window_days` - 3 calendar days | yes |
| `window_days` | stays 33 |

## Still open

- Whether mailbox.org accepts credentials for a feed subscription is untested and not
  needed: the URL itself is the secret (spec W5).
- How both consumers behave while the feed is unreachable: V-9, MAN-14.
- No duplicates over two refresh cycles with the real feed: MAN-3.
