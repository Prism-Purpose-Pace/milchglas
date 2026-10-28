@id:9106
Feature: Declined event frees the time
  The owner's booking page shows the time as free once the owner has declined an event.

  Scenario: A declined event found by the calendar-query REPORT leaves no busy block
    Given the owner's time zone is Europe/Berlin
    And calendar user 1042 invited the owner to an event on 6 November 2026 from 11:00 to 12:00
    And the owner declined that event
    When a refresh run completes
    Then the feed lists no busy block on 6 November 2026
