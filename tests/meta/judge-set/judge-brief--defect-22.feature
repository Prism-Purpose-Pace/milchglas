@id:9422
Feature: The window runs from today for 33 days
  A visitor sees the owner's busy times for the coming 33 days,
  which covers every booking window the owner offers.

  Background:
    Given today is 28 October 2026 in Europe/Berlin

  Scenario: Two overlapping events become one busy block
    Given the owner's calendar 'work' holds an event on 2 November 2026 from 09:00 to 10:30 UTC
    And it holds an event on 2 November 2026 from 10:00 to 11:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 11:00 UTC on 2 November 2026

  Scenario: An event on the first day of the window shows as busy
    Given the owner's calendar 'work' holds an event on 28 October 2026 from 15:00 to 16:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 15:00 to 16:00 UTC on 28 October 2026

  Scenario: An event after the window leaves no busy block
    Given the owner's calendar 'work' holds an event on 5 December 2026 from 15:00 to 16:00 UTC
    When the refresh run finishes
    Then the feed lists no busy block on 5 December 2026
