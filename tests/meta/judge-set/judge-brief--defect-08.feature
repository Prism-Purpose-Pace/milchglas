@id:9408
Feature: Transparent timed events leave the owner free
  A visitor can book a time the owner marked as free,
  so an event marked as free costs the owner no booking.

  Scenario: A transparent timed event leaves no busy block
    Given the owner's calendar 'sport' holds a transparent event on 16 November 2026 from 08:00 to 09:00 UTC
    When the refresh run finishes
    Then the feed lists no busy block on 16 November 2026
    But every line of the feed is at most 75 octets long

  Scenario: An opaque timed event shows as busy
    Given the owner's calendar 'sport' holds an opaque event on 16 November 2026 from 10:00 to 11:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 10:00 to 11:00 UTC on 16 November 2026
