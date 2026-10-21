# Test fixtures

Every fixture states where it comes from. Private event content is replaced by sentinels:
each title, description, location and attendee name starts with `BBX-`, and a malformed
value that a library might quote in an error message starts with `BBY-`. Tests assert
that neither prefix reaches a block, the feed or any error text.

| File | Origin | Cases |
|---|---|---|
| `objects/core-times.ics` | synthetic, RFC 5545 §3.6.1 (DTSTART alone, DTEND/DURATION), §3.3.6 (DURATION nominal days, exact time) and §3.3.5 (floating time); written in the dialect of a CalDAV object as stored, with a VTIMEZONE block | CORE-ZERO-1..3, CORE-DUR-1..5, all-day spans, malformed times |
| `objects/core-filter.ics` | synthetic, RFC 5545 §3.8.1.11 (STATUS), §3.8.2.7 (TRANSP), §3.8.4.1 and §3.2.12 (ATTENDEE, PARTSTAT), §3.8.1.3 (CLASS); other components per §3.6.2–§3.6.4 | CORE-FIL-1..12, CORE-FIL-14 |
| `objects/core-identity.ics` | synthetic, RFC 5545 §3.3.5 (DATE-TIME as UTC and with TZID), one instant in three spellings with their VTIMEZONE blocks | DET-7 |
| `objects/demo2.ics`, `objects/demo3.ics` | synthetic: the hand-written import fixtures of the live end-to-end suite (Nextcloud), copied with the former product name replaced | pipeline golden (AC-1, AC-3, AC-4, AC-5) |
| `expected_blocks.json` | the end-to-end suite's oracle for the two demo calendars, copied with the same renames | pipeline golden |

No fixture is captured from a CalDAV server yet. Synthetic files are replaced by
captured ones (sabre/dav via a Baïkal container) as the contract suite lands; a captured
file records server, version and date here.
