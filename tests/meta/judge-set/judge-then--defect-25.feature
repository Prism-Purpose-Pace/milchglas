@id:9225
Feature: Merging a packed Friday morning
  The owner's booking page shows a chain of overlapping events as one busy block.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: Two overlapping events on 6 November 2026
    Given calendar 'work' holds events on 6 November 2026 from 08:00 to 09:00 and from 08:30 to 09:30
    When a refresh run completes
    Then the feed lists one busy block on 6 November 2026 from 08:00 to 09:30

  Scenario: Three chained events on 6 November 2026
    Given calendar 'work' holds events on 6 November 2026 from 08:00 to 09:00, from 08:30 to 09:30 and from 09:15 to 10:30
    When a refresh run completes
    Then the busy block looks right
