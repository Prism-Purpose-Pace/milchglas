@id:9413
Feature: Only events inside the window reach the feed
  A visitor sees the owner's busy times from today on for 33 days,
  and can book any day after that without a stale busy block.

  Background:
    Given today is 28 October 2026 in Europe/Berlin

  Scenario Outline: The date of an event decides whether it shows as busy
    Given the owner's calendar 'work' holds an event on <date> from 09:00 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists <blocks> on <date>

    Examples:
      | date             | blocks         |
      | 28 October 2026  | one busy block |
      | 3 December 2026  | no busy block  |
      | 10 December 2026 | no busy block  |
