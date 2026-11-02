@id:9324
Feature: Ceil the end of a busy block to the grid
  A visitor never books the owner into the last minutes of an event,
  because every busy block ends on the next grid line.

  Background:
    Given the owner Maribel Quistorp keeps her calendars in the time zone Europe/Berlin
    And the grid is 15 minutes

  Scenario: An end at 10:05 moves on to 10:15
    Given the owner's calendar 'work' holds an event on 24 November 2026 from 09:00 to 10:05 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:15 UTC on 24 November 2026

  Scenario: An end on a grid line stays where it is
    Given the owner's calendar 'work' holds an event on 24 November 2026 from 13:00 to 13:45 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 13:00 to 13:45 UTC on 24 November 2026
