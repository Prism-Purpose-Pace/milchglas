@id:9402
Feature: Merge overlapping and touching busy blocks
  A visitor reads the owner's busy time as few, whole busy blocks,
  because busy blocks that overlap or touch become one.

  Scenario: Two overlapping events become one busy block
    Given the owner's calendar 'work' holds an event on 5 November 2026 from 09:00 to 10:00 UTC
    And it holds an event on 5 November 2026 from 09:30 to 11:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 11:00 UTC on 5 November 2026

  Scenario: Two events that touch become one busy block
    Given the owner's calendar 'work' holds an event on 5 November 2026 from 13:00 to 14:00 UTC
    And it holds an event on 5 November 2026 from 14:00 to 15:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 13:00 to 15:00 UTC on 5 November 2026
    And a visitor with a wrong feed token gets a not-found answer
