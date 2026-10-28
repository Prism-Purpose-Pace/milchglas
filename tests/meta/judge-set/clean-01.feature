@id:9501
Feature: Round busy blocks outward to the 15 minute grid
  The owner's booking page never offers a start that cuts into an event,
  because every busy block covers its event up to the grid lines around it.

  Background:
    Given today is 28 October 2026 in Europe/Berlin
    And the grid is 15 minutes

  Scenario: An event between grid lines grows to the lines around it
    Given calendar 'work' holds one event on 2 November 2026 from 09:10 to 09:50
    When a refresh run completes
    Then the feed lists one busy block on 2 November 2026 from 09:00 to 10:00

  Scenario Outline: Each edge moves only when it misses a grid line
    Given calendar 'work' holds one event on 2 November 2026 from <start> to <end>
    When a refresh run completes
    Then the feed lists one busy block on 2 November 2026 from <block_start> to <block_end>

    Examples:
      | start | end   | block_start | block_end |
      | 09:00 | 10:00 | 09:00       | 10:00     |
      | 09:01 | 10:00 | 09:00       | 10:00     |
      | 09:00 | 10:01 | 09:00       | 10:15     |
      | 09:14 | 09:16 | 09:00       | 09:30     |
