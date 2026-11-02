@id:9219
Feature: All-day events in the family calendar
  The owner's booking page keeps whole days free of bookings when the owner has blocked them.

  Scenario: An all-day event on 2 December 2026
    Given calendar 'family' holds an all-day event on 2 December 2026
    When a refresh run completes
    Then the feed lists one all-day busy block on 2 December 2026

  Scenario: An all-day event from 7 to 9 November 2026
    Given calendar 'family' holds an all-day event from 7 November 2026 to 9 November 2026
    When a refresh run completes
    Then the feed lists one all-day busy block from 7 November 2026 to 9 November 2026

  Scenario: An all-day event on 4 December 2026, the last full day of the window
    Given the window runs from 2 November 2026 to 5 December 2026
    And calendar 'family' holds an all-day event on 4 December 2026
    When a refresh run completes
    Then the result is as expected
