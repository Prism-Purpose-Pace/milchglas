@id:9125
Feature: Merging a crowded afternoon
  The owner's booking page shows a run of overlapping events as one busy block.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: Two overlapping events become one busy block
    Given calendar 'work' holds events on 25 November 2026 from 13:00 to 14:00 and from 13:30 to 15:00
    When a refresh run completes
    Then the feed lists one busy block on 25 November 2026 from 13:00 to 15:00

  Scenario: Three chained events become one busy block
    Given calendar 'work' holds events on 25 November 2026 from 13:00 to 14:00, from 13:30 to 15:00 and from 14:45 to 16:00
    When the refresher pushes the events onto a stack sorted by start and pops each overlap
    Then the feed lists one busy block on 25 November 2026 from 13:00 to 16:00
