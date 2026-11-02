@id:9428
Feature: Only enabled calendars reach the feed
  The owner decides which calendars make the owner busy,
  so a disabled calendar never blocks a booking.

  Background:
    Given the configuration enables the owner's calendar 'work'
    And it disables the owner's agenda 'sport'

  Scenario: An event in an enabled calendar shows as busy
    Given the calendar 'work' holds an event on 28 November 2026 from 10:00 to 11:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 10:00 to 11:00 UTC on 28 November 2026

  Scenario: An event in a disabled calendar leaves no busy block
    Given the calendar 'sport' holds an event on 28 November 2026 from 12:00 to 13:00 UTC
    When the refresh run finishes
    Then the feed lists no busy block on 28 November 2026 from 12:00 to 13:00 UTC
