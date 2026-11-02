@id:9529
Feature: Keep a timed event across midnight as one busy block
  The owner's late events block the evening and the early morning after it
  without splitting into two busy blocks.

  Background:
    Given today is 28 October 2026 in Europe/Berlin

  Scenario: An event from 22:00 to 02:00 stays one timed busy block
    Given calendar 'family' holds an event from 22:00 on 6 November 2026 to 02:00 on 7 November 2026
    When a refresh run completes
    Then the feed lists one busy block from 22:00 on 6 November 2026 to 02:00 on 7 November 2026
    And the feed lists no all-day busy block on either day

  Scenario: An event over a whole weekend stays one timed busy block
    Given calendar 'sport' holds an event from 18:00 on Friday 13 November 2026 to 20:00 on Sunday 15 November 2026
    When a refresh run completes
    Then the feed lists one busy block from 18:00 on 13 November 2026 to 20:00 on 15 November 2026
