@id:9302
Feature: Round busy blocks out to the quarter hour grid
  A visitor gets bookable times that line up with quarter hours,
  because every busy block starts and ends on the grid.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the grid is 15 minutes

  Scenario: A start between two grid lines moves back to the earlier one
    Given the owner's calendar 'work' holds an event on 4 November 2026 from 09:07 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:00 UTC on 4 November 2026

  Scenario: An end between two grid lines moves on to the later one
    Given the owner's calendar 'work' holds a short event on 4 November 2026 that starts at 11:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 11:00 to 11:15 UTC on 4 November 2026
