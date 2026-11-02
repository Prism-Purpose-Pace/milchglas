@id:9129
Feature: Window starts at midnight today
  The owner's booking page also shows the busy time earlier today, not only from now on.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the refresh run starts at 14:00 on 2 November 2026

  Scenario: An event this morning shows once window_start() returns midnight
    Given calendar 'work' holds an event on 2 November 2026 from 08:00 to 09:00
    When a refresh run completes
    Then the feed lists one busy block on 2 November 2026 from 08:00 to 09:00

  Scenario: An event yesterday leaves no busy block
    Given calendar 'work' holds an event on 1 November 2026 from 08:00 to 09:00
    When a refresh run completes
    Then the feed lists no busy block on 1 November 2026
