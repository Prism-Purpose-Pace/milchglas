@id:9409
Feature: Each busy block starts on the quarter hour before its event
  A visitor gets bookable times on quarter hours,
  because a busy block starts on the last grid line before its event.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the grid is 15 minutes

  Scenario Outline: A start moves back to the nearest earlier quarter hour
    Given the owner's calendar 'work' holds an event on 4 November 2026 from <start> to 12:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from <rounded> to 12:00 UTC on 4 November 2026

    Examples:
      | start | rounded |
      | 09:00 | 09:00   |
      | 09:01 | 09:00   |
      | 09:14 | 09:00   |
      | 10:01 | 10:00   |
