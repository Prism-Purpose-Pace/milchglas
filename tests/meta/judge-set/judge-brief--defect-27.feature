@id:9427
Feature: A refresh run picks up a changed event
  A visitor sees a moved event at its new time after the next refresh run,
  so the booking page never offers a time the owner has just filled.

  Scenario: A new event appears after the next refresh run
    Given the feed lists no busy block on 27 November 2026
    And the owner's calendar 'work' now holds an event on 27 November 2026 from 09:00 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:00 UTC on 27 November 2026

  Scenario: A moved event shows at its new time after the next refresh run
    Given the feed lists one busy block from 09:00 to 10:00 UTC on 27 November 2026
    And the owner moved that event in the calendar 'work' to 14:00 to 15:00 UTC on 27 November 2026
    When the sync finishes
    Then the feed lists one busy block from 14:00 to 15:00 UTC on 27 November 2026
