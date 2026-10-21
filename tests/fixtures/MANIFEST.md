# Test fixtures

Every fixture states where it comes from. Private event content is replaced by sentinels:
each title, description, location and attendee name starts with `BBX-`, and a malformed
value that a library might quote in an error message starts with `BBY-`. Tests assert
that neither prefix reaches a block, the feed or any error text.

| File | Origin | Cases |
|---|---|---|
| `objects/core-times.ics` | synthetic, RFC 5545 §3.6.1 (DTSTART alone, DTEND/DURATION), §3.3.6 (DURATION nominal days, exact time) and §3.3.5 (floating time); written in the dialect of a CalDAV object as stored, with a VTIMEZONE block | CORE-ZERO-1..3, CORE-DUR-1..5, all-day spans, malformed times |

No fixture is captured from a CalDAV server yet. Synthetic files are replaced by
captured ones (sabre/dav via a Baïkal container) as the contract suite lands; a captured
file records server, version and date here.
