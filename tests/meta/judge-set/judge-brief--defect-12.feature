@id:9412
Feature: Busy blocks with a gap between them stay apart
  A visitor can book the gap between two of the owner's events,
  while busy blocks that overlap or touch become one.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the grid is 15 minutes

  Scenario Outline: The gap after the first event decides how many busy blocks remain
    Given the owner's calendar 'work' holds an event on 5 November 2026 from 09:00 to 10:00 UTC
    And it holds an event on 5 November 2026 from <second start> to 11:00 UTC
    When the refresh run finishes
    Then the feed lists <blocks> on 5 November 2026

    Examples:
      | second start | blocks              |
      | 09:30        | one busy block      |
      | 10:15        | two busy blocks     |
      | 10:00        | one busy block      |
      | 10:30        | two busy blocks     |
