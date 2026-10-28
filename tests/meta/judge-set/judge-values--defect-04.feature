@id:9304
Feature: Keep busy blocks inside the 33 day window
  A visitor sees the owner's busy times for the coming 33 days,
  which covers every booking window the owner offers.

  Background:
    Given today is 28 October 2026 in Europe/Berlin

  Scenario: An event inside the window shows as busy
    Given the owner's calendar 'work' holds an event next week from 09:00 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:00 UTC

  Scenario: An event after the window leaves no busy block
    Given the owner's calendar 'work' holds an event on 3 December 2026 from 09:00 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists no busy block on 3 December 2026
