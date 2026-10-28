@id:9523
Feature: Combine the owner's calendars into one set of busy blocks
  A booking page reads each stretch of busy time once, however many of the
  owner's calendars hold an event in it.

  Background:
    Given today is 28 October 2026 in Europe/Berlin
    And the grid is 15 minutes

  Scenario: Overlapping events from three calendars form one busy block
    Given calendar 'work' holds an event on 2 November 2026 from 09:00 to 10:30
    And calendar 'family' holds an event on that day from 10:00 to 11:00
    And calendar 'sport' holds an event on that day from 10:50 to 12:00
    When a refresh run completes
    Then the feed lists one busy block on 2 November 2026 from 09:00 to 12:00

  Scenario: The same event in two calendars forms one busy block
    Given calendar 'work' and calendar 'family' each hold an event on 3 November 2026 from 12:00 to 13:00
    When a refresh run completes
    Then the feed lists one busy block on 3 November 2026 from 12:00 to 13:00
    And it lists no second busy block on that day
