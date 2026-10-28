# Test catalogue

Every observable behaviour that Milchglas tests, gates and manual checks pin, with a stable ID.
Spec: [spec.md](spec.md) (v0.5). Tests, issue checkboxes and reviews cite these IDs; nothing else
defines what "tested" means.

- **Citing.** A test carries the ID in its pytest id (`parametrize(ids=[...])`) or in its name
  (`test_..._core_clip_6`: lower case, dashes become underscores). A sub-case appends a suffix
  (`CORE-FIL-4-upper`). An issue checkbox starts with the ID it closes. A range such as
  `EMIT-2..5` in a test comment cites every ID in it. A short form without the area prefix
  (`ZERO-1` for `CORE-ZERO-1`) is not an ID.
- **New behaviour gets an ID here first.** Take the next free number of its prefix, then write
  the test. Never renumber or reuse an ID; a row changes only when the spec does.
- **Layer.** `unit` pure functions and fakes, default run · `property` Hypothesis or fuzz ·
  `contract` Baïkal container (`-m contract`) · `live` real Nextcloud (`-m live`) · `gate` CI,
  image or repository check · `manual` executed by the maintainer, result recorded in the docs.
- **Status.** `exists`: a test carries the ID. `planned`: none does yet.
- **Defaults.** `tz=Europe/Berlin`, `grid_minutes=15`, `owner_emails=["owner@example.org"]`;
  DST 2026: 03-29 and 10-25. Event content in fixtures starts with `BBX-`; a malformed value that
  a library might quote starts with `BBY-` (`tests/fixtures/MANIFEST.md`). `MAN-n` below are
  gates, not the goals G1 to G16 of the spec.

## 1. Parse (CalDAV answers, then the local-expansion fallback)

FR-2 fallback rows (`LOCAL-*`) are MVP only if V-4 fails, guarded per Q-18. `E2E-n` are defaults
the expected-blocks oracle assumes until the spec changes.

| ID | Behaviour | Verifies | Layer | Status |
|---|---|---|---|---|
| PARSE-1 | Captured answer for the seeded demo calendars, window pinned → blocks equal the committed expected-blocks file; every no-block event is absent | AC-1 to AC-5 | unit | planned |
| PARSE-2 | A 404 propstat for `calendar-data` is a parse error that fails the refresh; a 404 for any other requested property is ignored | NFR-C1, Q-14 | unit | planned |
| PARSE-3 | Server dialect parses: CRLF and LF-only lines, `&#13;`, folded lines, `X-` props, `calendar-data` as escaped text; CDATA and raw CRLF are synthetic robustness fixtures | NFR-C1 | unit | planned |
| PARSE-4 | Weekly series + EXDATE + moved instance → exactly the real occurrences; the override is its own VEVENT without RRULE and counts once; an instance whose override the owner declined is absent | AC-2, FR-2, FR-3 | unit | planned |
| PARSE-5 | Expanded instance with DURATION instead of DTEND (UTC DTSTART): the parser hands the DURATION text to reduce, builds no `timedelta` first (spy), and the length follows Q-20 | Q-20, AC-3 | unit | planned |
| PARSE-6 | Sentinel in SUMMARY, DESCRIPTION, LOCATION, ATTENDEE `CN`, CATEGORIES and `X-` props → absent from blocks (structural), feed and logs | AC-8, NFR-P1 | unit | planned |
| PARSE-7 | Empty 207 (zero responses) → zero blocks, not an error | Q-16 | unit | planned |
| PARSE-8 | Non-XML or truncated body → refresh fails; the error carries byte count and HTTP status, never body content | NFR-P4 | unit | planned |
| PARSE-9 | Fuzz: arbitrary bytes into the parse step → blocks or the module's own parse error, nothing else; no exception message holds a sentinel. The harness imports the package under `atheris.instrument_imports()` and keeps the literal line `import atheris`; dependency group limited to linux/amd64; one time-boxed, non-required CI job | NFR-C1 | property | planned |
| PARSE-10 | DOCTYPE or entity declaration in a multistatus → rejected before parsing (expat handler, stdlib only); entity bomb and external entity naming a local file → refresh fails, last feed byte-identical, no file read | Q-14, NFR-C1, NFR-O3 | unit | planned |
| PARSE-11 | One unparsable object among valid ones (garbage DTSTART; any parser error, including a non-empty `errors` list in lenient mode, even on a cancelled event) → refresh fails; the error names the object by href hash and the calendar by index; the sentinel is in no log or exception text | Q-14, NFR-P4, AC-8 | unit | planned |
| PARSE-12 | Expanded instance that still holds RRULE or RDATE while local expansion is off → unparsable → refresh fails, last feed kept | Q-14, FR-2 | unit | planned |
| PARSE-13 | Unfolding runs on bytes before UTF-8 decoding, CRLF + space and LF + space; a fold inside a multibyte character parses to the right text; a 200-octet line parses (the emitter stays strict, EMIT-7) | NFR-C1 | unit | planned |
| PARSE-14 | Out-of-range DURATION (for example `-P999999999DT1S`) → the source layer raises its malformed-event error; refresh fails, last feed kept, neither value nor event text in error or log | Q-14, NFR-P4 | unit | planned |
| PARSE-15 | Blocks parsed from the captured answer and emitted → exactly the committed feed bytes; goldens change only through an explicit update option | NFR-C1, AC-6 | unit | planned |
| E2E-1 | Oracle default: a timed block overlapping an all-day block stays separate; the no-overlap, no-touch rule applies per kind | Q-9, AC-1 | unit | planned |
| E2E-2 | Oracle default: an all-day event with `TRANSP:TRANSPARENT` blocks; `allday_mode` decides | Q-12, AC-5 | unit | planned |
| E2E-3 | Oracle default: the UID salt is the non-secret `uid_salt` of `config.json`, printed once by `init` | Q-13, D-7c | unit | planned |
| E2E-4 | Oracle default: the feed token is stored only as `token_sha256`; a plaintext `token` key is a configuration error | D-14, AC-22 | unit | planned |
| E2E-5 | Oracle default: the server's time-range only pre-filters; Milchglas clips to the window again | FR-1, FR-5 | unit | planned |
| LOCAL-DIFF-1 | For every scenario present in both `objects/` and `expanded/`, local expansion equals the parsed server answer block for block; a difference is a contract finding, never a test tweak | V-4, FR-2 | unit | planned |
| LOCAL-RR-1 | `UNTIL` as a date-only value ends the series on that day | FR-2 | unit | planned |
| LOCAL-RR-2 | `UNTIL` naive (floating) | FR-2 | unit | planned |
| LOCAL-RR-3 | `UNTIL` in UTC | FR-2 | unit | planned |
| LOCAL-RR-4 | `EXDATE` naive removes its instance | FR-2 | unit | planned |
| LOCAL-RR-5 | `EXDATE` with `TZID` removes its instance | FR-2 | unit | planned |
| LOCAL-RR-6 | `EXDATE;VALUE=DATE` removes the day, on an all-day and on a timed series | FR-2, L5 | unit | planned |
| LOCAL-RR-7 | `RDATE` adds its instance | FR-2, L5 | unit | planned |
| LOCAL-RR-8 | Open-ended RRULE is bounded to the window with bounded runtime | FR-2 | unit | planned |
| LOCAL-OVR-1 | Moved override replaces the instance at its new time | AC-2 | unit | planned |
| LOCAL-OVR-2 | Cancelled override removes the instance | AC-2 | unit | planned |
| LOCAL-OVR-3 | Override placed before its master in the object still applies | AC-2 | unit | planned |
| LOCAL-OVR-4 | Timed series with an all-day override (and the reverse) | AC-2, AC-5 | unit | planned |
| LOCAL-OVR-5 | Floating `RECURRENCE-ID` matches the parent's zone | AC-2 | unit | planned |
| LOCAL-OVR-6 | Owner declined only on the override → that instance is absent | FR-3 | unit | planned |
| LOCAL-FLT-1 | Floating 09:00–10:00 is read in `tz` (07:00Z in summer, 08:00Z in winter) with no warning; the server path reads it in the calendar's `calendar-timezone` | L11, Q-18 | unit | planned |
| LOCAL-TZ-1 | `TZID=W. Europe Standard Time` without VTIMEZONE → Europe/Berlin (the icalendar 7.3 mapping, pinned so an upgrade cannot regress silently) | NFR-C1 | unit | planned |
| LOCAL-TZ-2 | `TZID=Mitteleuropaeische Zeit` or `TZID=Foo/Bar` without VTIMEZONE → read in `tz`, exactly one warning whose only event-derived text is the TZID | NFR-C1, NFR-P4 | unit | planned |
| LOCAL-TZ-3 | Custom VTIMEZONE with a foreign TZID across a DST change → correct UTC | NFR-C1 | unit | planned |
| LOCAL-TZ-4 | `X-WR-TIMEZONE:Europe/Berlin` with a Z-stamped weekly series → wall-clock recurrence (08:00Z, then 07:00Z after 03-29) | FR-2 | unit | planned |
| LOCAL-DST-1 | Weekly 09:00 across both transitions keeps 09:00 local | AC-3 | unit | planned |
| LOCAL-DST-2 | 02:30 on 03-29 (nonexistent) takes the pre-gap offset: 02:30–03:30 → no block, 02:30–04:00 → 01:30Z–02:00Z | NFR-C1 | unit | planned |
| LOCAL-DST-3 | 02:30 on 10-25 (ambiguous) → first occurrence (`fold=0`, RFC 5545 section 3.3.5) | AC-3 | unit | planned |
| LOCAL-DST-4 | 01:30–03:30 on 10-25 → 3 real hours | AC-3 | unit | planned |
| LOCAL-POI-1 | Object with `DTSTART:BBY-garbage` among valid ones → parse error naming the href hash; refresh fails; `BBY-` is in no log record | Q-14, NFR-P4 | unit | planned |
| LOCAL-GRD-1 | Local expansion is off unless the explicit setting is on and a server error never turns it on; when on: per-run time budget, maximum instance count per object, `SECONDLY` and `MINUTELY` FREQ unparsable | Q-18 | unit | planned |

## 2. Filter (`reduce_event`)

| ID | Behaviour | Verifies | Layer | Status |
|---|---|---|---|---|
| CORE-FIL-1 | `STATUS:CANCELLED` → no block | AC-4, FR-3 | unit | exists |
| CORE-FIL-2 | `Status:cancelled` (mixed case) → no block | FR-3 | unit | exists |
| CORE-FIL-3 | `TRANSP:TRANSPARENT` on a timed event → no block; TRANSP absent or `OPAQUE` → block (`-transparent`, `-absent`, `-opaque`) | AC-4, FR-3 | unit | exists |
| CORE-FIL-4 | Owner `PARTSTAT=DECLINED` → no block; address compared lower-cased as a whole, `MAILTO:` and `mailto:` alike, second configured address too (`-upper`, `-lower`, `-second-address`) | AC-4, FR-3 | unit | exists |
| CORE-FIL-5 | Another attendee DECLINED, owner ACCEPTED → block | FR-3 | unit | exists |
| CORE-FIL-6 | Owner only as ORGANIZER, no owner ATTENDEE → block | FR-3 | unit | exists |
| CORE-FIL-7 | Owner ATTENDEE with `PARTSTAT=NEEDS-ACTION` or without PARTSTAT → block (`-needs-action`) | Q-19, FR-3 | unit | exists |
| CORE-FIL-8 | `CLASS:PRIVATE` → block; `CLASS:CONFIDENTIAL` as the read-only sharee receives it (SUMMARY rewritten, no STATUS, TRANSP or ATTENDEE) → block (`-private`, `-confidential`) | D-3, AC-4, L6 | unit | exists |
| CORE-FIL-9 | `STATUS:TENTATIVE` → block with `tentative=True` | FR-14 | unit | exists |
| CORE-FIL-10 | Owner `PARTSTAT=TENTATIVE` → `tentative=True` | Q-11 | unit | exists |
| CORE-FIL-11 | VTODO, VJOURNAL and VFREEBUSY components are ignored (`-todo`, `-journal`, `-freebusy`) | FR-3 | unit | exists |
| CORE-FIL-12 | All-day + `TRANSP:TRANSPARENT` → all-day block in `busy` mode: all-day events ignore TRANSP | Q-12, AC-5 | unit | exists |
| CORE-FIL-13 | LATER: `allday_mode=ignore` drops all-day blocks, `busy` keeps them (the MVP has `busy` only) | FR-13 | unit | planned |
| CORE-FIL-14 | The returned block type has exactly the timing fields and the tentative flag (`dataclasses.fields`), so no Class-A value survives reduction structurally | FR-4, NFR-P1 | unit | exists |

## 3. Reduce: length, duration, local times

| ID | Behaviour | Verifies | Layer | Status |
|---|---|---|---|---|
| CORE-ZERO-1 | `DTSTART == DTEND` → no block, decided before rounding: 09:07 and 09:00 behave alike (`-off-grid`, `-on-grid`) | NFR-C1 | unit | exists |
| CORE-ZERO-2 | `DTEND` before `DTSTART`, or a negative DURATION (also on the spring day) → no block, one warning that names the object only by its href hash | NFR-C1, NFR-P4 | unit | exists |
| CORE-ZERO-3 | Timed DTSTART without DTEND or DURATION → zero length (RFC 5545 section 3.6.1) → no block | NFR-C1 | unit | exists |
| CORE-DUR-1 | `DTSTART` + `DURATION:PT2H` → 2 h | NFR-C1 | unit | exists |
| CORE-DUR-2 | `VALUE=DATE` + `P2D` → 2-day all-day block | AC-5 | unit | exists |
| CORE-DUR-3 | `VALUE=DATE` without DTEND → 1 day | AC-5 | unit | exists |
| CORE-DUR-4 | `DTSTART;TZID=Europe/Berlin:20260328T090000` + `P1D` → ends 2026-03-29T07:00Z: the day is nominal, so the local end time stays 09:00 | Q-20, AC-3 | unit | exists |
| CORE-DUR-5 | Timed DTSTART with `DTEND;VALUE=DATE` (mixed kinds) → malformed → parse error, refresh fails | Q-14 | unit | exists |
| CORE-DUR-6 | DURATION days and weeks are nominal in the event's zone (`tz` for UTC and floating starts), the time part is exact: 2026-10-24 07:00Z + `P1D` ends 10-25 08:00Z, 03-28 08:00Z + `P1D` ends 03-29 07:00Z, a New York `P1D` over 11-01 is 25 h; `PT24H` and `PT36H` are real hours (03-28 08:00Z + `PT24H` ends 03-29 08:00Z) (`-zoned-autumn`, `-expanded-autumn`, `-expanded-spring`, `-week-and-time`, `-other-zone`) | Q-20, AC-3 | unit | exists |
| CORE-DUR-7 | `reduce_event` takes the raw DURATION text and reads RFC 5545 section 3.3.6 itself: `PT90M` equals `PT1H30M`; `+PT1H`, `PT30S`, `P1DT1H` and `P1W` parse; surrounding whitespace and a trailing CR are ignored; `PT0S`, `P0D` and `-PT0S` are empty, `-PT1M`, `-P1D` and `-P1DT2H` are negative (the sign belongs to the whole value) | Q-20, NFR-C1 | unit | exists |
| CORE-DUR-8 | DURATION text outside the grammar (empty, `P`, `PT`, `P1H`, `1D`, `PT1.5H`, `P1D2H`, `PT1S1M`, an Arabic-Indic digit, ten digits, free text) → `MalformedEventError` with the fixed text `DURATION is unreadable` and no chained exception; an event with a DURATION property and no text is malformed too, never read as "no duration", which would be a false free slot | Q-14, NFR-P4, AC-8 | unit | exists |
| CORE-MAL-1 | An event whose times cannot be read raises `MalformedEventError` and nothing else: no DTSTART, a garbled DTSTART or DURATION, a date start with a timed end or a time DURATION, a TZID with no definition (`Mars/Olympus`, on the start or the end), arithmetic past year 9999 (`P999999W`; an all-day 9999-12-31 plus `P2D`); the error text, `__cause__` and `__context__` hold nothing of the event | Q-14, NFR-P4, AC-8 | unit | exists |
| CORE-TZ-1 | Floating local time in the spring gap takes the pre-gap offset: 2026-03-29 02:30–03:30 → no block, 02:30–04:00 → 01:30Z–02:00Z | NFR-C1 | unit | exists |
| CORE-TZ-2 | Floating 02:30–03:00 on 2026-10-25 reads the first pass (`fold=0`): 00:30Z–02:00Z | AC-3 | unit | exists |
| CORE-TZ-3 | Zoned times beside the spring gap are ordered as instants, not as wall times: Europe/Berlin 2026-03-29 DTSTART 03:10 and DTEND 02:50 → 01:10Z–01:50Z (40 real minutes); DTSTART 02:30 (01:30Z) and DTEND 03:10 (01:10Z) → no block (`-wall-reversed`, `-instants-reversed`) | NFR-C1, AC-3 | unit | exists |
| PROP-13 | For any generated event `reduce_event` returns a block or a `Skip`, or raises `MalformedEventError`, and nothing else; the generator reaches all three kinds of outcome, so the property is not vacuous | FR-3, Q-14 | property | exists |
| PROP-14 | `reduce_event` for a UTC `DTSTART` and a DURATION beside a 2026 offset change returns exactly the interval a second computation gives, which uses no milchglas name and reads only the drawn case. Drawn: a zone of `available_timezones()`; 0 to 1 weeks, 0 to 2 days (also `P0D...`) and 0 to 240 exact minutes (`T<m>M` or `T<h>H<m>M`); the start is within three hours of one of the zone's 2026 changes (a zone with none gets a start anywhere in 2026), or, in half of the cases with a day or week part, that many days before the change plus or minus three hours, so the wall-clock end lands in the gap, in the fold or just beside it. The rule of the second computation: without a day or week part, the start's UTC instant plus the exact minutes; otherwise the days and weeks added as wall time in `tz`, a missing or ambiguous wall time read with `fold=0` (the offset before a gap, the first occurrence in a fold), then the exact minutes added as real time. A zero-length result is `Skip.EMPTY`, any other a `TimedBlock` with that start and end. Explicit examples (start, DURATION): Berlin 2026-10-25 01:10Z `PT30M`, 01:30Z `PT1H` and 01:10Z `P1DT30M`; Lord_Howe 2026-04-04 15:10Z `PT10M`; Berlin 2026-03-28 01:30Z `P1D` (the end in the spring gap) and 00:30Z `P1DT2H` (the exact part crosses the change); Africa/Cairo 2026-04-22 22:00Z `P1D` (the gap opens at midnight). Reach, one test per kind: the generator finds within 20000 draws a start in the second pass of a fold with an exact part only, a day-part end in a fold, a day-part end in a gap, and an exact part that crosses a change after a day part, so the property is not vacuous | Q-20, FR-4, AC-3 | property | exists |

## 4. Clip, round, merge

| ID | Behaviour | Verifies | Layer | Status |
|---|---|---|---|---|
| CORE-CLIP-1 | Block Sun 23:50 → Mon 00:10 local, window from Mon 00:00 → [00:00, 00:10] | FR-5 | unit | exists |
| CORE-CLIP-2 | Block ending exactly at the window start → no block | FR-5 | unit | exists |
| CORE-CLIP-3 | Block starting exactly at the window end → no block | FR-5 | unit | exists |
| CORE-CLIP-4 | Block straddling the window end → cut at the end | FR-5 | unit | exists |
| CORE-CLIP-5 | All-day block straddling the window start → `start_date` is the window start date | FR-5 | unit | exists |
| CORE-CLIP-6 | Window start = 00:00 local of `clock.now()`; refreshes at 09:05 and 09:20 the same day → identical window and bytes | FR-5, AC-6 | unit | exists |
| CORE-RND-1 | 10:07–10:52 → 10:00–11:00 | FR-6 | unit | exists |
| CORE-RND-2 | 10:00–10:15 stays unchanged | FR-6 | unit | exists |
| CORE-RND-3 | 10:00–10:16 → 10:00–10:30 | FR-6 | unit | exists |
| CORE-RND-4 | Grid 30: 10:07–10:52 → 10:00–11:00; grid 5 → 10:05–10:55 (`-grid-30`, `-grid-5`) | FR-6 | unit | exists |
| CORE-RND-5 | 2026-10-25 01:40Z–01:50Z (02:40–02:50 CET, second pass of the fold) → 01:30Z–02:00Z | AC-3, FR-6 | unit | exists |
| CORE-RND-6 | 00:40Z–00:50Z (02:40 CEST, first pass) → 00:30Z–01:00Z | AC-3, FR-6 | unit | exists |
| CORE-RND-7 | 2026-03-29 00:40Z–00:50Z (01:40 CET, before the gap) → 00:30Z–01:00Z; 01:05Z–01:10Z (03:05 CEST) → 01:00Z–01:15Z, and at grid 60 → 01:00Z–02:00Z (`-before-gap`, `-after-gap`, `-grid-60`) | AC-3, FR-6 | unit | exists |
| CORE-RND-8 | `grid_minutes` must divide 1440 and every UTC-offset change of `tz` within 366 days after the run: 7, 25, 50 rejected; Europe/Berlin accepts 15, 30, 60 and rejects 45, 90, 120; Asia/Kolkata accepts 45, 90, 120; Australia/Lord_Howe rejects 60; grid 60 with Kolkata (+05:30) floors 10:07–10:52 IST to 10:00–11:00 IST (wall-time grid, not an epoch grid) | AC-22, FR-6 | unit | exists |
| CORE-RND-9 | 2026-10-25 02:07–02:20 with `fold=1` (second pass) rounds to 01:00Z–01:30Z at grid 15 and to 01:00Z–02:00Z at grid 60; at the grids the zone check rejects the block still widens by the offset in force at each instant (45 and 90 → 00:30Z–02:00Z, 120 → 01:00Z–03:00Z); a local datetime is never rebuilt from components, which loses `fold` | AC-22, AC-3 | unit | exists |
| CORE-RND-10 | `grid_fits_zone(grid, tz, start)` counts the UTC-offset changes in the 366 days after `start` and no others (one 365 days away counts, one 367 days away or in the past does not), measured in minutes: Asia/Pyongyang's 30-minute change rejects 45 and accepts 30, Africa/Cairo's 60-minute change at midnight fits 60 and not 120, UTC fits every divisor of 1440; `start` must be timezone-aware; the grid it rejects is the one that leaves a rounded edge off the local grid (Berlin, 45, spring-forward day: the end lands on 03:15 CEST and rounding it again moves it) | FR-6, AC-22 | unit | exists |
| CORE-MRG-1 | [9,12) + [10,11) + [11:30,12:30) → [9,12:30) | AC-1, FR-6 | unit | exists |
| CORE-MRG-2 | Adjacent [9,10) + [10,11) → [9,11) | AC-1, FR-6 | unit | exists |
| CORE-MRG-3 | [9,10) + [10:15,11) → two blocks | AC-1 | unit | exists |
| CORE-MRG-4 | Tentative and confirmed overlapping → one block, tentative only if every contributor is tentative (`-mixed`, `-all-tentative`) | Q-10 | unit | exists |
| CORE-MRG-5 | All-day 10-17→10-19 + 10-19→10-20 → 10-17→10-20; timed and all-day blocks never merge with each other (`-days`, `-kinds-apart`) | Q-9, AC-1 | unit | exists |
| CORE-PIPE-1 | Demo calendars through reduce, clip, round and merge with the window pinned → exactly the oracle blocks | AC-1, AC-3 to AC-5 | unit | exists |
| PROP-1 | Merge output is sorted and `a.end < b.start` strictly for consecutive blocks of the same kind | AC-1, FR-6 | property | exists |
| PROP-2 | `merge(merge(x)) == merge(x)`; `round(round(x)) == round(x)` for every (zone, grid) pair the AC-22 check admits | FR-6, AC-22 | property | exists |
| PROP-3 | Set-union semantics: a minute is covered by the output iff some rounded input covers it | D-7b | property | exists |
| PROP-4 | For any zone and any divisor of 1440, a rounded start never moves later and an end never earlier, by less than one grid step; every emitted block is at least one step long; on admitted pairs both edges sit on the local wall-time grid | FR-6, L3 | property | exists |
| PROP-5 | `merge(shuffle(x)) == merge(x)` | FR-6 | property | exists |
| PROP-6 | `clip` output lies inside the window; no intersection → no output; clip then round equals round then clip on grid-aligned windows | FR-5 | property | exists |
| PROP-11 | Over Europe/Berlin, Asia/Kolkata, Asia/Kathmandu and Australia/Lord_Howe × every divisor of 1440: direction and bound always hold; edges sit on the local grid and rounding is idempotent exactly for the pairs the AC-22 check admits | FR-6, AC-22 | property | planned |

## 5. Emit

| ID | Behaviour | Verifies | Layer | Status |
|---|---|---|---|---|
| EMIT-1 | Property names of every VEVENT are exactly UID, DTSTAMP, DTSTART, DTEND, SUMMARY, TRANSP, STATUS | NFR-P3, AC-8 | unit | exists |
| EMIT-2 | Header lines exact: `VERSION:2.0`, `PRODID:-//Milchglas//<version>//DE`, `X-WR-CALNAME:Privat (busy)` (a constant), `REFRESH-INTERVAL;VALUE=DURATION:PT15M`, `X-PUBLISHED-TTL:PT15M`; `ttl_seconds=3600` → `PT1H`; no `METHOD` line, so DTSTAMP keeps its last-revision meaning | FR-7, D-8 | unit | exists |
| EMIT-3 | Timed block → `DTSTART:20260601T070000Z` form only: no TZID, no offset, no fractional seconds; no VTIMEZONE anywhere | D-8, FR-7 | unit | exists |
| EMIT-4 | All-day block → `DTSTART;VALUE=DATE:20261003` and `DTEND;VALUE=DATE:20261005` | AC-5 | unit | exists |
| EMIT-5 | `TRANSP:OPAQUE` and `STATUS:CONFIRMED` on every block (LATER: `tentative_mode=separate` → `STATUS:TENTATIVE`) | D-8, FR-14 | unit | exists |
| EMIT-6 | SUMMARY `Blocker, Privat; A\B` → `SUMMARY:Blocker\, Privat\; A\\B`; a literal `\N` stays a backslash and an N; checked against a fixed vector table, not through icalendar's `vText`; any control character in the summary (newline, U+2028) is a configuration error, never escaped | FR-7, AC-22 | unit | exists |
| EMIT-7 | 120-character summary with umlauts → every line at most 75 octets, continuation starts with one space, no split UTF-8 sequence or text escape, unfold equals input; a 75-octet line stays, 76 folds; fixed vectors | NFR-C1 | unit | exists |
| EMIT-8 | CRLF everywhere including after `END:VCALENDAR`; no bare LF or CR | FR-7, NFR-C1 | unit | exists |
| EMIT-9 | VEVENTs ordered all-day blocks first, then timed, each by `(start, end)`; the order is total, so the bytes are canonical | AC-6 | unit | exists |
| EMIT-10 | Re-parsing the feed with `icalendar` gives the same blocks (also PROP-8) | NFR-C1 | unit | exists |
| PROP-7 | The whole pure pipeline run twice on the same input gives identical bytes | AC-6, D-7c | property | exists |
| PROP-8 | Emit, then `icalendar` parse, equals the merged input blocks | NFR-C1 | property | exists |
| PROP-9 | `uid(salt, a) == uid(salt, b)` iff kind, start and end are equal; format `^[0-9a-f]{32}@milchglas$` | D-7c, AC-6 | property | exists |
| PROP-10 | The feed invariants hold for every generated feed: NFR-P3 whitelist, UTC or `VALUE=DATE` only, unique UIDs, sorted, blocks pairwise disjoint and non-adjacent per kind, lines at most 75 octets, CRLF | AC-1, AC-8, NFR-P3 | property | exists |
| PROP-12 | `stamps` returns the DTSTAMP of every UID of an emitted feed | D-7c | property | exists |

## 6. Determinism

| ID | Behaviour | Verifies | Layer | Status |
|---|---|---|---|---|
| DET-1 | Two refreshes, identical fetch bodies, clock +15 min → byte-identical `feed.ics` | AC-6 | unit | planned |
| DET-2 | An unchanged block keeps the DTSTAMP recorded in the previous feed file after the clock advances | AC-6, D-7c | unit | planned |
| DET-3 | One event moved → exactly one UID disappears and one appears with `DTSTAMP == clock.now()`; every other line is unchanged | AC-6 | unit | planned |
| DET-4 | No previous feed → every DTSTAMP equals `clock.now()`; on an unchanged run none does | AC-6 | unit | planned |
| DET-5 | `uid_salt` change → every UID changes (documented); same salt → stable; the salt comes only from `config.json` | Q-13, D-7c | unit | exists |
| DET-6 | 365 daily refreshes with a fake clock over fixtures spanning both DST days: invariants hold every day, bytes change only on days the window boundary crosses a block, DTSTAMPs of persisting blocks never change, runtime at most 2 s | AC-6, NFR-C1 | unit | planned |
| DET-7 | The same instant as `…Z`, `TZID=Europe/Berlin` and `TZID=America/New_York` → identical UID and identical feed bytes | D-7c, NFR-C1 | unit | exists |
| DET-8 | Unreadable previous feed (truncated, not UTF-8, not a calendar) does not stop the refresh: every DTSTAMP equals now and one warning with counts only is logged | D-7c, AC-6 | unit | planned |
| DET-9 | Under `python -m milchglas`, `zoneinfo.TZPATH` is empty (set once in `__main__`, never in `core/`), so the pinned `tzdata` decides every DST rule and the feed bytes do not depend on the host | NFR-O3, FR-6 | unit | exists |

## 7. Orchestration and config (fakes: scripted fetcher, fake clock, `tmp_path`)

| ID | Behaviour | Verifies | Layer | Status |
|---|---|---|---|---|
| ORCH-FETCH-1 | 10 s timeout reaches the opener; a timeout is retried: four attempts with injected backoff 1, 2, 4 s, then failure | FR-1, Q-15 | unit | exists |
| ORCH-FETCH-2 | 500, 502, 503 retried; every 4xx, `401`, `403` and `429` included, fails at once after exactly one request (a retry would deepen a brute-force lockout); one 503 then 207 → success | FR-1, Q-15 | unit | exists |
| ORCH-FETCH-3 | Any fetch or parse failure → `feed.ics` bytes and mtime unchanged, `last_error` set, `last_success` unchanged, one-shot exit code 1 | AC-7, D-7d, FR-8 | unit | planned |
| ORCH-FETCH-4 | Body over the 16 MiB cap → aborted mid-stream, failure as in FETCH-3 | Q-15 | unit | planned |
| ORCH-FETCH-5 | 301, 302, 307 never followed → failure whose error names the status and the Location host; a second port named in `Location` receives no request | NFR-S7 | unit | planned |
| ORCH-FETCH-6 | Basic auth header built from `CALDAV_USER` and `CALDAV_SECRET` | FR-1, NFR-S2 | unit | planned |
| ORCH-FETCH-7 | REPORT carries `Depth: 1`; its body has `<C:time-range>` and `<C:expand>` over the same UTC window (`…Z`); only `enabled` calendars are requested, in config order | FR-1, AC-10 | unit | planned |
| ORCH-FETCH-8 | PROPFIND `Depth: 0` guard before each REPORT fails the refresh (feed kept, calendar named by index) when the href is a collection but no calendar, the owner is the service user, or the privilege set holds `{DAV:}write`; a read-only calendar passes; a 207 without responses on a non-calendar never reaches success | FR-1, NFR-S3, Q-16 | unit | planned |
| ORCH-FETCH-9 | The first request already carries `Authorization` (exactly one request per successful fetch, none without it); a `Set-Cookie` is never sent back | FR-1 | unit | planned |
| ORCH-FETCH-10 | Calendars are fetched, parsed and reduced one at a time: with ten fake calendars at most one response body is alive (counter in the fake transport) | Q-15 | unit | planned |
| ORCH-FETCH-11 | A refused connection is not retried: one attempt, then a failure that names the refused connection (only timeouts and 5xx are retried) | FR-1, Q-15 | unit | planned |
| ORCH-NET-1 | `CALDAV_URL` with an untrusted TLS certificate fails the refresh; the feed stays byte-identical | NFR-S7 | unit | planned |
| ORCH-NET-2 | A server answering in a slow drip ends the run at the total deadline (default 120 s, injected); the refresh fails, the feed stays byte-identical | NFR-S7 | unit | planned |
| ORCH-NET-3 | The contract suite's plain-HTTP switch is test-only: production code never reads it, so with the switch absent an `http` URL is rejected | NFR-S7 | unit | planned |
| ORCH-WRITE-1 | Success → unique temp file in the feed's own directory, `fsync`, `os.replace`, directory `fsync`; no `*.tmp` left; `feed.ics` mode `0644`, var dir `0700` | FR-8, NFR-S4 | unit | exists |
| ORCH-WRITE-2 | Failure injected after the temp write, before the replace → old feed intact, temp file removed | AC-7, FR-8 | unit | exists |
| ORCH-WRITE-3 | Crash injected between `os.replace` and the state write → next run: byte-identical feed, state repaired | AC-6, AC-7 | unit | planned |
| ORCH-WRITE-4 | State is written atomically; a corrupt or missing `state.json` counts as absent, the refresh still works, `/healthz` is 503 until the next success | FR-8, FR-11 | unit | planned |
| ORCH-WRITE-5 | Injected `ENOSPC` (full disk) → previous feed byte-identical | AC-7, FR-8 | unit | exists |
| ORCH-CFG-1 | `enabled: false` edited between two runs → that calendar's blocks are gone, no restart; config is re-read every refresh, also after an edit that replaces the file (write and rename) | AC-10, FR-12 | unit | planned |
| ORCH-CFG-2 | Invalid config fails before any request, keeps the old feed and names only the field: unknown `tz`, a `grid_minutes` that fails CORE-RND-8, empty `calendars`, zero calendars with `enabled: true`, duplicate hrefs, `owner_emails` not a list | AC-22, Q-16 | unit | planned |
| ORCH-CFG-3 | Missing `CALDAV_SECRET` → exit 2, message names the variable only | NFR-S2, NFR-O1 | unit | planned |
| ORCH-CFG-4 | Unknown key → rejected, names the key never the value; a key named like the secret variable is rejected too; the committed example configuration holds no secret, is refused naming `uid_salt` as committed and passes the loader once an `init`-shaped salt is pasted; a `uid_salt` other than 32 lower-case hex characters is rejected | AC-22, NFR-S2 | unit | exists |
| ORCH-CFG-5 | No `window_days` → 33-day window; 0 and 91 rejected, 1 and 90 accepted | D-6, AC-22 | unit | exists |
| ORCH-CFG-6 | Missing `uid_salt` → exit non-zero, names the key, no request, old feed kept; `refresh` never generates a salt | Q-13, AC-22, NFR-O1 | unit | planned |
| ORCH-CFG-7 | Plaintext `token` key → rejected, names the field never the value; `token_sha256` that is not 64 hex characters → refresh fails | D-14, AC-22 | unit | planned |
| ORCH-CFG-8 | Control character in a string that reaches the output (`summary`) → configuration error before any request | FR-7, AC-22 | unit | planned |
| ORCH-CFG-9 | `CALDAV_URL` not `https` → refresh fails before any request, keeps the feed, names only the variable | NFR-S7, AC-22 | unit | planned |
| ORCH-CFG-10 | Hrefs `https://other/x`, `//other/x`, `file:///etc/passwd`, `/a/../b`, `/a/%2e%2e/b` → configuration error with zero outbound requests; a valid href with percent-encoding is requested byte for byte | NFR-S7, AC-22 | unit | planned |
| ORCH-CFG-11 | A changed configuration logs the names of the changed keys, never values (toggling `enabled` logs one line naming the key) | AC-22 | unit | planned |
| ORCH-CFG-12 | `MILCHGLAS_CONFIG` names the configuration file for `refresh` and `web`; unset, it is `./config.json` | D-16 | unit | planned |
| ORCH-EMPTY-1 | Every enabled calendar passes the guard and returns zero events → valid header-only feed written, invariants pass, `last_success` set; distinct from a failure | Q-16, NFR-R1 | unit | planned |
| ORCH-EMPTY-2 | State records the returned object count per calendar; a calendar dropping from non-zero to zero, and a feed dropping from non-empty to zero blocks, each record one warning with counts only in state and log | Q-16 | unit | planned |
| ORCH-LOG-1 | Full refresh over fixtures with sentinels (also malformed SUMMARY, DESCRIPTION, LOCATION) at `MILCHGLAS_LOG_LEVEL=DEBUG` → no log record (message, args, exception text), no stdout or stderr line, no state field holds a sentinel | AC-8, NFR-P1 | unit | planned |
| ORCH-LOG-2 | `CALDAV_SECRET`, its base64 form, the `Authorization` header and the feed token (distinct injected values) appear in no log record, exception text, stdout or stderr, state field or HTTP response | AC-8, NFR-S2, NFR-S5 | unit | planned |
| ORCH-LOG-3 | A library error whose message quotes the value (`BBY-`) → the record holds exception class, calendar index and HTTP status only; no line names a calendar or an href | NFR-P4, AC-8 | unit | planned |
| ORCH-LOG-4 | Exactly one summary line per refresh with counts only: calendars, objects, blocks, duration, outcome | NFR-O1, NFR-P4 | unit | planned |
| ORCH-LOG-5 | `DEBUG` never enables `http.client` debug output; a `401`, `429` or timeout reports status or exception class only, no credential text | NFR-P4, NFR-S2 | unit | planned |
| ORCH-LOOP-1 | `--loop --interval 900` with fake clock and injected sleep runs at t0, t0+900, …; a failing run does not end the loop | FR-10 | unit | planned |
| ORCH-LOOP-2 | SIGTERM during a run → the run finishes its write, exit 0; SIGTERM while sleeping → immediate exit (in-process handler call, plus one subprocess smoke test with a real signal) | NFR-O1 | unit | planned |
| ORCH-LOCK-1 | Second refresh while the var-dir lock is held → non-zero exit, feed and state untouched, one complete feed remains | FR-8, AC-7 | unit | planned |
| ORCH-CLI-1 | `refresh --now 2026-09-28T00:00:00+02:00` pins the clock; a naive `--now` is rejected | FR-5 | unit | planned |
| ORCH-CLI-2 | `refresh --dry-run` prints counts and timestamps only, writes neither feed nor state (mtimes unchanged) and takes no lock; no command prints raw source data | NFR-O1 | unit | planned |
| ORCH-CLI-3 | `init` prints once the token and the members `"uid_salt"` and `"token_sha256"` (hex SHA-256 of the token as UTF-8 bytes) and writes no file: working directory, state directory and `config.json` are unchanged | D-14, NFR-O1, Q-13 | unit | exists |
| ORCH-CLI-4 | `rotate-token` prints a new token and its `"token_sha256"` and writes no file; the token is the URL-safe encoding of 32 CSPRNG bytes (256 bits), two runs differ | D-14, NFR-S1, AC-20 | unit | exists |
| ORCH-CLI-5 | The printed token appears nowhere except the output of `init` and `rotate-token` (logs, state, feed, config searched) | NFR-S2, NFR-S5 | unit | exists |

## 8. Web (WSGI, direct `environ` calls, no server)

| ID | Behaviour | Verifies | Layer | Status |
|---|---|---|---|---|
| WEB-1 | `GET /f/<token>.ics` → 200 with `Content-Type: text/calendar; charset=utf-8`, quoted `ETag`, `Content-Length`, `X-Robots-Tag: noindex`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, `Cache-Control: private, max-age=0`; no versioned `Server` header | AC-9, NFR-S1, Q-17 | unit | exists |
| WEB-2 | Methods GET, HEAD, OPTIONS, POST × right or wrong token × `If-None-Match` and `Range` × path variants (`/`, `/f/`, `/f/<token>.ics/x`, `/robots.txt`, `/f/../state`, `%2e%2e%2f`, `%00`, `//f/`, `.ICS`, trailing slash, `;` parameters, double encoding): every wrong-token response equals the unknown-path response in status, body and headers (apart from `Date`); the 404 carries `X-Content-Type-Options` and `Cache-Control`, and its body is `Not Found` and a newline (empty for `HEAD`) with `Content-Length: 10` | AC-9, Q-17 | unit | exists |
| WEB-3 | `If-None-Match` equal → 304 without body; different → 200; the ETag is unchanged across refreshes of an unchanged source | AC-9, AC-6 | unit | exists |
| WEB-4 | `HEAD` → same headers, empty body; `POST`, `PUT`, `DELETE`, `OPTIONS` on any path → the identical 404 | AC-9 | unit | exists |
| WEB-6 | Feed file missing (never refreshed) → the identical 404, not a server error | FR-9, AC-9 | unit | exists |
| WEB-7 | A successful feed fetch, a `304` revalidation included, writes one log line with the client network (/24 IPv4, /48 IPv6) and a user-agent class; no log line holds the token, a part of it or any part of `token_sha256` | NFR-S5, AC-21 | unit | exists |
| WEB-8 | The token is only hashed (UTF-8 bytes, SHA-256) and compared with `hmac.compare_digest`, never joined into a path; a spy sees exactly one digest comparison per request on every 404 path, unknown paths and unsupported methods included, and no file open before a 404 except the timed `config.json` re-read, once per 60 s tick whatever the request presents | AC-9, NFR-S1 | unit | exists |
| WEB-9 | Non-ASCII token (`/f/ä.ics`), empty token and a token of another length → the identical 404, not a server error | AC-9, NFR-S1 | unit | exists |
| WEB-10 | `web` refuses to start when any `CALDAV_*` variable is set; the error names the variable only | D-13 | unit | exists |
| WEB-11 | Import graph: `milchglas.web` imports neither `milchglas.sources` nor `milchglas.refresh` (`from milchglas import refresh` included), so a lazy refresh cannot creep in | D-13 | unit | exists |
| WEB-12 | After the printed `token_sha256` is pasted, within one refresh interval (injected clock) the old token returns the identical 404 and the new one 200, without a restart; under Option A no file in the state directory is named after any token | AC-20, D-14 | unit | exists |
| WEB-13 | `web` refuses to start on a `token_sha256` that is not 64 hex characters | NFR-S1, D-14 | unit | exists |
| WEB-18 | Feed file unreadable (permission, a directory, an I/O error) → the identical 404 and one constant warning naming the exception class; no exception leaves the app, so no server error log line carries the request path or the token | NFR-S5, AC-9 | unit | exists |
| WEB-19 | `web` reads `MILCHGLAS_LOG_LEVEL` in any letter case, unset or empty means `INFO`; any other value refuses the start with an error naming only the variable | NFR-O1 | unit | exists |

## 9. Health

| ID | Behaviour | Verifies | Layer | Status |
|---|---|---|---|---|
| WEB-5 | `/healthz` → 200 when `last_success` is under 60 min old and `token_sha256` is readable; 503 when older, when state is missing or unreadable, and while the digest is unreadable; the body is identical in both states and holds no timestamps or counts; the same holds on the app's own wall clock, which production uses | FR-11, Q-23 | unit | exists |
| WEB-14 | Run-time re-read finds a malformed or truncated `token_sha256`, or an unparsable `config.json`: `web` keeps the last valid digest (old token 200, anything else the identical 404), logs one line naming the key (no value) on every re-read, `/healthz` is 503; after the fix it is 200 and the new token works within one re-read | Q-23, FR-11 | unit | exists |
| WEB-15 | An invalid unrelated key (for example `grid_minutes` 7) beside a valid `token_sha256`: the right token still gets 200 and `/healthz` is unaffected, because `web` reads only `token_sha256` | Q-23, NFR-S1 | unit | exists |
| WEB-16 | Refresh against an unreachable source: the feed is unchanged and `/healthz` turns 503 once 60 min have passed (fake clock) | AC-7, FR-11 | unit | planned |
| WEB-17 | Container health check tests liveness only: with `state.json` two hours old `/healthz` is 503 and the `web` container stays `healthy`; it passes on any HTTP answer, 200 or 503 (a stub answering 503 → exit 0), and fails only when nothing answers | AC-21, FR-11, D-7d | gate | planned |

## 10. Gates (`GATE-n` automated, `MAN-n` executed by the maintainer; results go into `docs/consumers.md` or `docs/runbook.md`)

| ID | Behaviour | Verifies | Layer | Status |
|---|---|---|---|---|
| GATE-1 | `ruff`, `mypy --strict` and `pytest` with branch coverage of at least 90 % pass in CI | AC-12 | gate | planned |
| GATE-2 | Every wheel in the runtime closure (walked from the package metadata of the installed environment, which `uv sync --locked` builds from `uv.lock`) is `py*-none-any` with `Root-Is-Purelib: true`; negative control: a platform wheel name fails | NFR-O3, AC-12 | gate | exists |
| GATE-3 | CI check over the Compose file and Dockerfile fails on a missing hardening key (`cap_drop`, `read_only`, `no-new-privileges`), a `FROM` without digest and any `pip install`; negative control: a Compose file without `cap_drop` fails; the Compose file defines exactly `web` and `refresher` (loop interval 900, only `web` publishes a port) and no CalDAV value; the dependency-update config covers the image and holds the 3.12 minor | AC-13, D-12, D-13 | gate | planned |
| GATE-4 | Built image: based on `python:3.12-slim`, holds only the runtime dependencies of the lock file and no test files; the configured user is not root and the image config defines no CalDAV user, secret or token; changing the user to root fails the test | AC-13, NFR-S2, NFR-S4 | gate | planned |
| GATE-5 | Container started with the Compose settings (read-only root, `/tmp` tmpfs, all capabilities dropped, `no-new-privileges`) serves the feed and `/healthz`; the process runs as a user other than 0; a filesystem diff shows writes only inside the state volume; gunicorn runs with `--no-control-socket`, a worker timeout and no access log, and logs no startup warning; `docker inspect` shows `ReadonlyRootfs`, `CapDrop` and `SecurityOpt` on both services | AC-13, NFR-S4 | gate | planned |
| GATE-6 | Smoke run (one command) against a seeded Baïkal: both services start, the first refresh completes, the right token gets 200 with the feed, `/healthz` 200, a wrong token the identical 404; `docker stop` lets the refresher finish its write and exit 0 within the default stop timeout | FR-9, FR-10, AC-9 | gate | planned |
| GATE-7 | In the built image `zoneinfo.TZPATH` is empty, so the pinned `tzdata` decides every DST rule | NFR-O3, FR-6 | gate | planned |
| GATE-8 | Refresh in the built image against a scripted source, with a dummy secret in the environment and a dummy token from `init`, leaves neither value in container logs, feed, state file or image configuration | NFR-S2, NFR-S5 | gate | planned |
| GATE-9 | The Compose memory limit rests on a recorded measurement of the peak memory of parsing one 16 MiB response plus headroom; the refresher stays inside it on the largest allowed response | Q-15, NFR-S4 | gate | planned |
| GATE-10 | The secret scan over the full Git history carries a rule for 256-bit URL-safe tokens and no new ignore rule; a planted token fails it | D-14, NFR-S2 | gate | planned |
| GATE-11 | Every `python -m milchglas` command in `docs/runbook.md` and `docs/consumers.md` is accepted by the real argument parser; a command with a nonexistent option fails | NFR-O1, AC-14 | gate | planned |
| GATE-12 | Every fixture file is listed in `tests/fixtures/MANIFEST.md` with its origin (captured: server, version, date; synthetic: RFC 5545 section) and, for Nextcloud captures, the user language; the public-tree guard and the secret scan pass on it | NFR-C1 | gate | planned |
| GATE-13 | Spec drift: the backticked config keys of `docs/spec.md` equal the key list of `CLAUDE.md` (a missing and an extra key both fail), no other document names a config key outside them, and the spec holds no placeholder threshold ("stated bound"); a missing required file or spec anchor exits 2 and never passes; the fixtures are the real documents, mutated | AC-12, AC-22 | gate | exists |
| GATE-14 | `milchglas.core` stays pure: every import is on an allowlist (`icalendar` by name and only `Component`, not as a tree: `icalendar.cli` reads files), relative imports never climb out of core, `open`, `eval`, `exec`, `compile`, `__import__` and clock calls are rejected, and core stays a package so the scan cannot go silently empty; each rule has a failing and a silent case | AC-6, G8 | gate | exists |
| GATE-15 | Every (grid, zone) pair that `grid_fits_zone` accepts, over every zone of the tz database and every grid from 1 to 1440, can be drawn by the property strategies, and no drawn pair is rejected; a lost corner, an extra pair and a hand-picked list each fail | AC-22, FR-6 | gate | exists |
| GATE-16 | A test oracle is not a copy of the code it checks: no `re.compile` pattern literal under `tests/` appears verbatim as a string under `src/`, and no test imports a `_`-prefixed name from `milchglas.core`; a copied pattern and a private import each fail | AC-12 | gate | exists |
| GATE-17 | The catalogue and the tests agree: every catalogue-shaped token under `src/` and `tests/` equals a row ID (or a row ID with a lowercase suffix), every row with status `exists` is cited by a test, and every row a test cites has status `exists`; each check has a failing and a silent case | AC-12 | gate | exists |
| GATE-18 | The suite run inside a git hook: inherited `GIT_*` variables (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` planted at a decoy repository) reach no test, so the repository-building tests pass and the decoy stays byte-identical | AC-12 | gate | exists |
| GATE-19 | The review rules agree: every rule in `REVIEW.md` has a unique `RV-` ID and one of the levels `BLOCK P0`, `BLOCK P1`, `WARN`, `INFO`; every rule ID that `REVIEW.md` or `AGENTS.md` cites is defined in `REVIEW.md`; `AGENTS.md` lists exactly the `BLOCK` rules, each under the priority of its level, and no `WARN` or `INFO` rule; every test-catalogue ID that `REVIEW.md` names is a row with status `exists`; each check has a failing and a silent case | AC-12 | gate | exists |
| GATE-20 | The suite runs in a host zone with DST and a half-hour offset, pinned in `tests/conftest.py`, so code that converts to local time where UTC is meant (a lost `astimezone(UTC)`) moves a block and fails a test; a test fails when the pin is lost | FR-7, AC-12 | gate | exists |
| GATE-21 | No string literal under `src/` names a content-bearing iCalendar property (SUMMARY, DESCRIPTION, LOCATION, ATTENDEE, ORGANIZER and the other text, people, place and link properties of RFC 5545 and RFC 7986), compared case-insensitively, so private content has no source to flow from; the only exceptions, each in its exact spelling, are ATTENDEE in `_owner_replies` (the owner's PARTSTAT) and the config key `summary`, and an exception that no longer occurs fails; planted reads in any case and any function fail, while the emitter's `SUMMARY:` line, other properties and prose stay silent | FR-4, NFR-P1, AC-8 | gate | exists |
| GATE-22 | Every scenario under `tests/features/` runs under its catalogue ID: exactly one ID tag among its own, its rule's and its feature's tags, and that tag is a row; exactly one function binds it with literal `@scenario("<path>", "<name>")` arguments, named `test_<id>` or `test_<id>_…`, unless the scenario carries `@backlog`, which lets it stay unbound and skips it when bound; neither an ID tag nor a feature's `@id:<ticket>` becomes a marker while every other tag still meets `--strict-markers`; each check has a failing and a silent case | AC-12 | gate | exists |
| MAN-1 | Test feed with the shipped header (no `METHOD`), two UTC timed events and one `VALUE=DATE` event: subscribed in mailbox.org, connected in meetergo, which blocks the timed test slot and the all-day test day on the meeting type in use; record propagation time, whether `PT15M` is honoured and how the all-day block shows; every meeting type's booking window is at most `window_days` - 3 | AC-0.1, AC-0.2, AC-0.4, V-1, V-5, Q-2 | manual | planned |
| MAN-2 | Fallback when a consumer rejects the `METHOD`-less header (`METHOD:PUBLISH` returns) or the all-day block (`allday_mode=busy` then emits timed 00:00–24:00 local blocks, and EMIT-4 and CORE-MRG-5 change) | D-8, AC-0.1, AC-0.2 | manual | planned |
| MAN-3 | No duplicates in mailbox.org after two refresh cycles; blocks are not deleted and re-added | AC-6, V-7 | manual | planned |
| MAN-5 | meetergo does not offer a slot that overlaps a private block; mailbox.org shows the block within 30 minutes of the private change | AC-11, L1 | manual | planned |
| MAN-6 | Deployed images: the platform lists `CALDAV_URL`, `CALDAV_USER` and `CALDAV_SECRET` runtime-only and locked, set on `refresher` only; after every deployment that adds or changes a variable, `docker history --no-trunc` of each service image holds none of the three names (count 0); runs with MAN-8 | AC-13, OR4 | manual | planned |
| MAN-7 | An external monitor polls `/healthz` at least every 5 min; with the refresher made to fail (wrong password) the e-mail alert arrives after the 60-minute threshold | AC-19, OR6 | manual | planned |
| MAN-8 | One fetch with a canary token leaves zero hits in proxy, platform and app logs; the canary path returns the identical 404; the plain-HTTP router answers 404 for `/f/*`, never a redirect | AC-21, OR5, NFR-S5 | manual | planned |
| MAN-9 | A loop fetching the feed every second for a whole redeploy sees no non-200 answer, and neither does a loop on `/healthz` while the source is healthy | AC-21 | manual | planned |
| MAN-10 | Source outage over 60 min: the right token still gets 200 with the last good feed through the proxy; `web` stays routed and `healthy`, also with `state.json` two hours old | AC-21, D-7d | manual | planned |
| MAN-11 | The environment of the running `web` container holds no `CALDAV_*`; if the platform injects every variable into every service, `web` refuses to start until the Compose file scopes them | D-13, OR4 | manual | planned |
| MAN-12 | Service user: read-only shares only, quota `0 B`, app password without filesystem access, no system address book, no events of its own, no calendar delegate; a WebDAV file `PUT` fails; revoking the app password → next refresh fails, previous feed identical, `/healthz` 503 after 60 min; a new app password → next refresh succeeds | NFR-S3, D-2, OR3, AC-7 | manual | planned |
| MAN-13 | Each runbook procedure (rotate token, swap calendar, recover from a stale feed, migrate host, force a refresh) is executed once against a real deployment, one checked line per NFR-O2 item; `docs/consumers.md` has one field per AC-0.1 and AC-0.2 observation; an empty field fails the review | AC-14, NFR-O2 | manual | planned |
| MAN-14 | With the feed answering 404, 503 and a timeout, meetergo still blocks the test slot and refuses a booking, and mailbox.org keeps its blocks | V-9 | manual | planned |
| MAN-15 | A hello-world container deployed first: the platform's edge proxy routes the chosen subdomain to it with TLS and without a manual proxy | V-8, OR2 | manual | planned |

## 11. Contract (Baïkal, `-m contract`; each `C-*` captures its fixture) and live

`tests/contract/QUIRKS.md` holds one row per observed server behaviour: behaviour · evidence · the
test that pins it. The default contract run diffs against the committed fixtures; a sabre upgrade
shows as fixture drift. `--capture-fixtures` regenerates them with sanitised hosts and hrefs.

| ID | Behaviour | Verifies | Layer | Status |
|---|---|---|---|---|
| C-PROPFIND-1 | PROPFIND lists the service user's calendars with `displayname`, `calendar-timezone` (present or absent, recorded), `resourcetype`, owner and `current-user-privilege-set`, the properties the FR-1 guard reads | V-2, FR-1, L11 | contract | planned |
| C-DEPTH-1 | REPORT at a `Depth` other than 1, or at an href that is not a calendar, → 207 without responses | FR-1 | contract | planned |
| C-EXP-1 | Weekly series + EXDATE + moved override → instances in UTC, no VTIMEZONE, the override once | V-4, AC-0.3, AC-2 | contract | planned |
| C-EXP-2 | Override with `STATUS:CANCELLED` → the instance is present with that STATUS, as AC-0.3 expects; pinned as observed | AC-0.3, V-4 | contract | planned |
| C-EXP-3 | Override with owner `PARTSTAT=DECLINED` only → the instance carries that ATTENDEE | FR-3, AC-2 | contract | planned |
| C-EXP-4 | Expand-shape asserts on every captured answer: no RRULE, RDATE, EXDATE or VTIMEZONE in any instance; each instance of a recurring object has a RECURRENCE-ID distinct within its UID, single events none, overrides keep their own properties; all-day instances stay `VALUE=DATE`; every timed DATE-TIME is UTC | AC-0.3, NFR-C2 | contract | planned |
| C-FLT-1 | Floating 09:00 in a calendar without `calendar-timezone` → 09:00Z; with `calendar-timezone` Europe/Berlin → 07:00Z | L11, AC-0.3 | contract | planned |
| C-TZ-1 | `TZID=W. Europe Standard Time` object with its Outlook VTIMEZONE → correct UTC after expand | V-4 | contract | planned |
| C-DUR-1 | Expanded instance of a DURATION object keeps DURATION with a UTC DTSTART (sabre/vobject 4.5.6) | Q-20 | contract | planned |
| C-DUR-2 | `P1D` across 2026-03-29 and 2026-10-25 arrives as sent; reduce then ends an instance starting 03-28 08:00Z at 03-29 07:00Z | Q-20, AC-3 | contract | planned |
| C-DST-1 | Daily 09:00 Berlin across 10-25 → 07:00Z, 07:00Z, 08:00Z | AC-3 | contract | planned |
| C-DATE-1 | All-day objects keep `VALUE=DATE` through expand | AC-5 | contract | planned |
| C-RANGE-1 | Event ending exactly at the window start (floating and DATE variants): returned or not is recorded; the client re-clips either way | E2E-5, FR-5 | contract | planned |
| C-EMPTY-1 | Empty calendar → 207 with zero responses | Q-16 | contract | planned |
| C-ERR-1 | Unknown href → 404; wrong password → 401 | FR-1 | contract | planned |
| C-SIZE-1 | 2 000 instances → the response parses; wall time is recorded as a budget, not asserted | Q-15 | contract | planned |
| C-VER-1 | The suite records the Baïkal, sabre/dav and sabre/vobject versions (`composer show`) in `QUIRKS.md`; a vobject other than 4.5.6 is a recorded deviation; the container is pinned by digest | NFR-C2 | contract | planned |
| C-L5-1 | Each L5 silent drop is pinned as observed: overridden instance without master, RDATE-only series starting before the window, RRULE series with one RDATE, daily series beyond 3500 iterations; a reproduced drop fails V-4 | L5, V-4 | contract | planned |
| MAN-4 | Live suite on the real server records each AC-0.3 capture as observed: instance count and response size; the L5 drops; `EXDATE;VALUE=DATE` on a timed series; two RDATEs; `P1D` across both transitions; a cancelled override; a declined invitation written by the owner's client; CONFIDENTIAL as the sharee receives it; one all-day event per client with its TRANSP; one floating event; the REPORT with redirects disabled | AC-0.3, V-2, V-4, L5, L11, Q-12 | live | planned |
