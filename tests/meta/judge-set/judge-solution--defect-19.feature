@id:9119
Feature: All-day event over several days
  The owner's booking page shows an all-day event that spans several days as busy on each of them.

  Scenario: An all-day event from 23 to 25 November 2026 is kept as one entry in the interval list
    Given calendar 'family' holds an all-day event from 23 November 2026 to 25 November 2026
    When a refresh run completes
    Then the feed lists one all-day busy block from 23 November 2026 to 25 November 2026

  Scenario: An all-day event on 30 November 2026 alone shows as one all-day busy block
    Given calendar 'family' holds an all-day event on 30 November 2026
    When a refresh run completes
    Then the feed lists one all-day busy block on 30 November 2026
