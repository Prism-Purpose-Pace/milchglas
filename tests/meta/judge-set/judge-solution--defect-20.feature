@id:9120
Feature: Cancelled evening of a weekly series
  The owner's booking page frees the evening when one instance of a weekly event is cancelled.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: The cancelled Thursday leaves no busy block
    Given calendar 'sport' holds an event every Thursday from 19:00 to 20:30, first on 5 November 2026
    And the instance on 12 November 2026 is cancelled
    And the client retries the fetch of calendar 'sport' up to 3 times on a timeout
    When a refresh run completes
    Then the feed lists no busy block on 12 November 2026

  Scenario: The Thursday after the cancelled one stays busy
    Given calendar 'sport' holds an event every Thursday from 19:00 to 20:30, first on 5 November 2026
    And the instance on 12 November 2026 is cancelled
    When a refresh run completes
    Then the feed lists one busy block on 19 November 2026 from 19:00 to 20:30
