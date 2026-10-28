@id:9415
Feature: The configured grid decides where a busy block starts
  An owner who offers quarter-hour, half-hour or hourly bookings
  gets busy blocks that start on a line of that grid.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario Outline: A start moves back to the last line of the configured grid
    Given the grid is <grid> minutes
    And the owner's calendar 'work' holds an event on 12 November 2026 from <start> to 12:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from <rounded> to 12:00 UTC on 12 November 2026

    Examples:
      | grid | start | rounded |
      | 15   | 09:20 | 09:15   |
      | 30   | 09:20 | 09:00   |
      | 15   | 10:20 | 10:15   |
      | 60   | 09:20 | 09:00   |
