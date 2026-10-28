@id:9515
Feature: Handle calendars without events
  A booking page shows the owner as free when the calendars are empty, and
  the operator hears of a calendar that suddenly turned empty.

  Background:
    Given today is 28 October 2026 in Europe/Berlin

  Scenario: Three empty calendars give a feed without busy blocks
    Given the calendars 'work', 'family' and 'sport' hold 0 events between 28 October and 30 November 2026
    When a refresh run completes
    Then the feed lists no busy block
    But it still opens with the line "BEGIN:VCALENDAR"

  Scenario: A calendar that turns empty leaves a warning in the log
    Given calendar 'sport' held 6 events at the refresh run at 10:00
    And it holds 0 events at the refresh run at 10:15
    When the refresh run at 10:15 completes
    Then the log holds a warning with the counts 6 and 0
