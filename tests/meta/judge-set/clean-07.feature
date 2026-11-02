@id:9507
Feature: Keep busy blocks at the owner's local hour across the end of summer time
  A subscriber in any time zone sees each busy block at the hour the owner
  wrote it, on both sides of the switch on 25 October 2026.

  Background:
    Given today is 20 October 2026 in Europe/Berlin
    And the grid is 15 minutes

  Scenario Outline: An event at 09:00 local time keeps its hour after the switch
    Summer time ends at 03:00 on 25 October 2026: 24 October runs at UTC+2, 25 October at UTC+1.

    Given calendar 'work' holds an event on <day> from 09:00 to 10:00 local time
    When a refresh run completes
    Then the feed holds the line "<start_line>"
    And the feed holds the line "<end_line>"

    Examples:
      | day             | start_line               | end_line               |
      | 24 October 2026 | DTSTART:20261024T070000Z | DTEND:20261024T080000Z |
      | 25 October 2026 | DTSTART:20261025T080000Z | DTEND:20261025T090000Z |
