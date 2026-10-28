@id:9203
Feature: All-day event on a Monday in November
  The owner's booking page offers no time on a day the owner has blocked in full.

  Scenario: An all-day event on 16 November 2026 shows as an all-day busy block
    Given calendar 'family' holds an all-day event on 16 November 2026
    When a refresh run completes
    Then the feed lists one all-day busy block on 16 November 2026
    And the all-day event is handled properly
