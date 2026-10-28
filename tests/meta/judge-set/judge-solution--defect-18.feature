@id:9118
Feature: Disabled calendar stays out of the feed
  The owner takes a calendar off the booking page with one switch in the configuration.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: An event in a disabled calendar leaves no busy block
    Given the refresher caches the calendar list for 15 minutes
    And the configuration lists calendar 'family' as disabled
    And calendar 'family' holds an event on 18 November 2026 from 19:00 to 21:00
    When a refresh run completes
    Then the feed lists no busy block on 18 November 2026

  Scenario: An event in an enabled calendar shows as a busy block
    Given the configuration lists calendar 'family' as enabled
    And calendar 'family' holds an event on 18 November 2026 from 19:00 to 21:00
    When a refresh run completes
    Then the feed lists one busy block on 18 November 2026 from 19:00 to 21:00
