@id:9310
Feature: Round busy blocks to the owner's own grid
  A visitor gets bookable times that line up with the owner's grid,
  because every busy block starts and ends on one of its lines.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the owner uses a coarse grid

  Scenario: A start at 09:20 moves back to 09:00
    Given the owner's calendar 'work' holds an event on 10 November 2026 from 09:20 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:00 UTC on 10 November 2026

  Scenario: An end at 11:10 moves on to 11:30
    Given the owner's calendar 'work' holds an event on 10 November 2026 from 11:00 to 11:10 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 11:00 to 11:30 UTC on 10 November 2026
