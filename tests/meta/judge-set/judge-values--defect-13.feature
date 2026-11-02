@id:9313
Feature: Cancelled events free the owner
  A visitor can book a time whose event was cancelled,
  so the owner loses no booking to an event that no longer takes place.

  Scenario: A cancelled event leaves no busy block
    Given the owner's calendar 'foo' holds a cancelled event on 11 November 2026 from 10:00 to 11:00 UTC
    When the refresh run finishes
    Then the feed lists no busy block on 11 November 2026

  Scenario: A confirmed event next to a cancelled one stays busy
    Given the owner's calendar 'work' holds a cancelled event on 11 November 2026 from 10:00 to 11:00 UTC
    And it holds a confirmed event on 11 November 2026 from 11:00 to 12:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 11:00 to 12:00 UTC on 11 November 2026
