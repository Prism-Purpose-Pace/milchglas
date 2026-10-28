@id:9109
Feature: Overlapping events in work and sport
  The owner's booking page shows overlapping events from two calendars as one busy block.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: Events in 'work' and 'sport' that overlap become one busy block
    Given calendar 'work' holds an event on 12 November 2026 from 17:00 to 18:00
    And calendar 'sport' holds an event on 12 November 2026 from 17:30 to 19:00
    When a refresh run completes
    Then the feed lists one busy block on 12 November 2026 from 17:00 to 19:00 after exactly 4 requests to the server

  Scenario: Events in 'work' and 'sport' on different days stay apart
    Given calendar 'work' holds an event on 12 November 2026 from 17:00 to 18:00
    And calendar 'sport' holds an event on 13 November 2026 from 17:00 to 18:00
    When a refresh run completes
    Then the feed lists one busy block on 12 November 2026 and one on 13 November 2026, each from 17:00 to 18:00
