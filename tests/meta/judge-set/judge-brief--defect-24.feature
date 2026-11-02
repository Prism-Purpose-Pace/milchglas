@id:9424
Feature: Events from all calendars merge into shared busy blocks
  A visitor sees one busy block where events from the owner's calendars overlap,
  so the booking page offers no time that one of them takes up.

  Scenario: Overlapping events from two calendars become one busy block
    Given the owner's calendar 'work' holds an event on 24 November 2026 from 09:00 to 10:00 UTC
    And the owner's calendar 'family' holds an event on 24 November 2026 from 09:30 to 11:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 11:00 UTC on 24 November 2026

  Scenario: Events from two calendars with a gap stay apart
    Given the owner's calendar 'work' holds an event on 24 November 2026 from 13:00 to 14:00 UTC
    And the owner's calendar 'sport' holds an event on 24 November 2026 from 15:00 to 16:00 UTC
    When the refresh run finishes
    Then the feed lists two busy slots on 24 November 2026, from 13:00 to 14:00 UTC and from 15:00 to 16:00 UTC
