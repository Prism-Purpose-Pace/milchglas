@id:9401
Feature: Floor the start of a busy block to the grid
  A visitor gets bookable times on quarter hours,
  because each busy block starts on the 15 minute grid.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the grid is 15 minutes

  Scenario: A start at 09:07 moves back to 09:00
    Given the owner's calendar 'work' holds an event on 4 November 2026 from 09:07 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:00 UTC on 4 November 2026
    And the health check reports the feed as fresh

  Scenario: A start on a grid line stays where it is
    Given the owner's calendar 'work' holds an event on 4 November 2026 from 11:15 to 12:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 11:15 to 12:00 UTC on 4 November 2026
