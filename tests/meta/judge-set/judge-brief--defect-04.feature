@id:9404
Feature: Clip busy blocks to the 33 day window
  A visitor sees the owner's busy times for the coming 33 days,
  and nothing from before today.

  Background:
    Given today is 28 October 2026 in Europe/Berlin

  Scenario: An event before today leaves no busy block
    Given the owner's calendar 'work' holds an event on 27 October 2026 from 09:00 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists no busy block on 27 October 2026

  Scenario: An event after the window leaves no busy block
    Given the owner's calendar 'work' holds an event on 4 December 2026 from 09:00 to 10:00 UTC
    And it holds an event on 6 November 2026 from 09:00 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists no busy block on 4 December 2026
    And the busy block on 6 November 2026 carries the summary 'Blocker Privat'
