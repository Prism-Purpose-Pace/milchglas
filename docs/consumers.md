# Consumer setup: mailbox.org and meetergo

This page describes how the two consumers read the Milchglas feed (spec OR10, D-4) and
records which gates passed (AC-0.1, AC-0.2, AC-0.4; MAN-1). Host names, feed URLs, tokens,
account names, calendar names and details of an operator's account do not belong here; the
maintainer keeps the detailed record privately.

## Handing over the feed URL

The feed URL is `https://<host>/f/<token>.ics`. `init` or `rotate-token` prints the token
once on the server; afterwards the server holds only its SHA-256 (spec D-14).

- The URL is the secret. Copy it from the server terminal straight into the consumer's
  dialog.
- Never send it by mail, chat or link shortener, and never open it in a browser tab: link
  previews, mail scanners, history and extensions store it (threat model T-35).
- Whoever knows the URL sees only anonymous blocks; after a rotation (`rotate-token`) the
  new URL is entered in both consumers.

## mailbox.org (iCal feed subscription)

Once, in the web client:

1. Arrow next to *Neuer Termin* → *Von URL (iCal) importieren* → *iCal-Feed abonnieren*.
2. Paste the feed URL and confirm.
3. The calendar appears under *Meine Kalender*. It is read-only.

mailbox.org honours the feed's `REFRESH-INTERVAL` (`PT15M`), not the 7-day Open-Xchange
default.

## meetergo (ICS calendar)

Once per profile, not per meeting type: meetergo connects an ICS calendar in the profile
(entry *Proton/ICS Calendar*), and it applies to every meeting type of that profile
(meetergo help "Connecting ICS calendars", as of 2026-09-16).

- meetergo requires a publicly reachable HTTPS URL without authentication.
- Every event in the ICS calendar blocks, all-day ones included; only events marked free
  and cancelled ones do not (meetergo help, as of 2026-07-28). Milchglas writes every block
  as `TRANSP:OPAQUE` and `STATUS:CONFIRMED`.
- Booking window: no meeting type may be bookable more than `window_days` - 3 calendar days
  ahead (default 33 - 3 = 30). A window counted in weekdays is longer in calendar days; an
  unlimited window is not allowed. A new meeting type starts with 30 calendar days. Before
  extending a window, raise `window_days` in `config.json` (spec L2, Q-2).

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
