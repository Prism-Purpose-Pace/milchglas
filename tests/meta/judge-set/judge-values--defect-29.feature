@id:9329
Feature: The window starts at local midnight today
  A visitor sees the owner's busy times from the start of today,
  measured in the owner's time zone.

  Background:
    Given the owner's time zone is Europe/Berlin
    And today is 29 October 2026

  Scenario: An event earlier today shows as busy
    Given the owner's calendar 'work' holds an event on 29 October 2026 from 06:00 to 07:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 06:00 to 07:00 UTC on 29 October 2026

  Scenario: An event that ended yesterday leaves no busy block
    Given the owner's calendar 'work' holds an event on 28 October 2026 from 20:00 to 21:00 UTC
    When the refresh run finishes
    Then the feed lists no busy block on 28 October 2026

  Scenario: An event across local midnight keeps its part from today
    Given Lio Brask invited the owner to an event on 28 October 2026 from 22:30 to 23:30 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 23:00 to 23:30 UTC on 28 October 2026
