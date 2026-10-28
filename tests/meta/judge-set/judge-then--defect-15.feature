@id:9215
Feature: Family and work events on the same evening
  The owner's booking page shows events from two calendars that overlap as one busy block.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: Events in 'family' and 'work' that overlap become one busy block
    Given calendar 'family' holds an event on 27 November 2026 from 18:00 to 19:30
    And calendar 'work' holds an event on 27 November 2026 from 19:00 to 20:00
    When a refresh run completes
    Then the feed lists one busy block on 27 November 2026 from 18:00 to 20:00
    But the overlap causes no issue
