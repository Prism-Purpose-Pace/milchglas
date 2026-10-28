@id:9502
Feature: Merge busy blocks that touch or overlap
  A booking page reads one busy block per stretch of busy time, so the
  owner's day shows no seam between back-to-back events.

  Background:
    Given today is 28 October 2026 in Europe/Berlin
    And the grid is 15 minutes

  Scenario: Back-to-back events in two calendars become one busy block
    Given calendar 'work' holds an event on 2 November 2026 from 09:00 to 10:00
    And calendar 'family' holds an event on 2 November 2026 from 10:00 to 11:00
    When a refresh run completes
    Then the feed lists one busy block on 2 November 2026 from 09:00 to 11:00
    And the feed lists no other busy block on that day

  Scenario: A gap of one grid step keeps two busy blocks
    Given calendar 'work' holds an event on 2 November 2026 from 09:00 to 10:00
    And calendar 'work' holds an event on 2 November 2026 from 10:15 to 11:00
    When a refresh run completes
    Then the feed lists a busy block on 2 November 2026 from 09:00 to 10:00
    And it lists a second busy block on that day from 10:15 to 11:00
