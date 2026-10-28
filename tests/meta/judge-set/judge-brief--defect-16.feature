@id:9416
Feature: Rounding keeps busy blocks on the quarter hour grid
  A visitor gets bookable times on quarter hours,
  because every busy block starts and ends on the grid.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the grid is 15 minutes

  Scenario: A start at 09:10 moves back to 09:00
    Given the owner's calendar 'work' holds an event on 13 November 2026 from 09:10 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:00 UTC on 13 November 2026

  Scenario: An end at 11:05 moves on to 11:15
    Given the owner's calendar 'work' holds an event on 13 November 2026 from 10:30 to 11:05 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 10:30 to 11:15 UTC on 13 November 2026

  Scenario: A wrong feed token gets the answer for an unknown address
    Given the owner's feed token is 'h8Wc3NpQ6tRz'
    When a visitor asks for the feed with the token 'b2Kx9MvL4fGs'
    Then the visitor gets the same not-found answer as for an unknown address
