@id:9410
Feature: Each busy block ends on the half hour after its event
  An owner who offers half-hour bookings never gets booked into the end of an event,
  because a busy block ends on the next half hour.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the grid is 30 minutes

  Scenario Outline: An end moves on to the next half hour
    Given the owner's calendar 'work' holds an event on 10 November 2026 from 08:00 to <end> UTC
    When the refresh run finishes
    Then the feed lists one busy block from 08:00 to <rounded> UTC on 10 November 2026

    Examples:
      | end   | rounded |
      | 10:00 | 10:00   |
      | 10:01 | 10:30   |
      | 11:01 | 11:30   |
      | 10:29 | 10:30   |
