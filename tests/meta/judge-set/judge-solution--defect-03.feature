@id:9103
Feature: All-day event in the family calendar
  The owner's booking page shows a day blocked in the family calendar as busy, so nobody books into it.

  Scenario: An all-day event on 9 November 2026 blocks that whole day
    Given calendar 'family' holds an all-day event on 9 November 2026
    When the XML parser walks the answer of calendar 'family' element by element
    Then the feed lists one all-day busy block on 9 November 2026
