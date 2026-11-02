@id:9323
Feature: Overlapping events from own and shared calendars merge
  A visitor sees one busy block where the owner's events overlap,
  whichever calendar each of them comes from.

  Scenario: An own and a shared event that overlap become one busy block
    Given these calendars hold an event on 23 November 2026:
      | calendar | shared by       | start UTC | end UTC |
      | work     | nobody          | 09:00     | 10:00   |
      | family   | Corvin Ashgrove | 09:30     | 10:30   |
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:30 UTC on 23 November 2026
