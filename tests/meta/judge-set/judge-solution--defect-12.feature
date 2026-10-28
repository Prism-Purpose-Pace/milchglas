@id:9112
Feature: Events past the window stay out of the feed
  The owner's booking page shows only the coming 33 days, so far-off plans stay private.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: An event the day after the window leaves no busy block
    Given the refresher stores each event as a tuple of two epoch integers
    And the window runs from 2 November 2026 to 5 December 2026
    And calendar 'work' holds an event on 6 December 2026 from 09:00 to 10:00
    When a refresh run completes
    Then the feed lists no busy block on 6 December 2026

  Scenario: An event the day before the window ends shows as a busy block
    Given the window runs from 2 November 2026 to 5 December 2026
    And calendar 'work' holds an event on 4 December 2026 from 09:00 to 10:00
    When a refresh run completes
    Then the feed lists one busy block on 4 December 2026 from 09:00 to 10:00
