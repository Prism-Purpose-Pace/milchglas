@id:9322
Feature: Adjacent busy blocks merge into one
  A visitor sees one busy block where the owner's events follow each other,
  so the booking page offers no gap that is not there.

  Scenario: Two events back to back in one calendar become one busy block
    Given the owner's calendar 'work' holds an event on 22 November 2026 from 09:00 to 10:00 UTC
    And it holds an event on 22 November 2026 from 10:00 to 11:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 11:00 UTC on 22 November 2026

  Scenario: Back to back events from two calendars become one busy block
    Given Ilka's calendar 'sport' is shared with the owner and holds an event on 22 November 2026 from 14:00 to 15:00 UTC
    And the owner's calendar 'work' holds an event on 22 November 2026 from 15:00 to 16:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 14:00 to 16:00 UTC on 22 November 2026
