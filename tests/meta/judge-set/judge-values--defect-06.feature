@id:9306
Feature: An event across midnight stays one busy block
  A visitor sees the owner as busy until the event ends,
  even when it ends after midnight.

  Scenario: An evening event that ends after midnight is one busy block
    Given the owner's calendar 'family' holds an event that starts late in the evening of 6 November 2026 and ends at 01:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block that ends at 01:00 UTC on 7 November 2026

  Scenario: An event that ends at local midnight leaves the next day free
    Given the owner's calendar 'family' holds an event on 6 November 2026 from 22:00 to 23:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 22:00 to 23:00 UTC on 6 November 2026
