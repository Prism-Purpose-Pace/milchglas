@id:9105
Feature: Cancelled event drops out of the feed
  The owner's booking page frees the time of a cancelled event; to get there the refresher
  retries every calendar three times with an exponential backoff.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: A cancelled event on 5 November 2026 leaves no busy block
    Given calendar 'work' holds a cancelled event on 5 November 2026 from 14:00 to 15:00
    When a refresh run completes
    Then the feed lists no busy block on 5 November 2026

  Scenario: A confirmed event at the same hour still shows as a busy block
    Given calendar 'work' holds a confirmed event on 5 November 2026 from 14:00 to 15:00
    When a refresh run completes
    Then the feed lists one busy block on 5 November 2026 from 14:00 to 15:00
