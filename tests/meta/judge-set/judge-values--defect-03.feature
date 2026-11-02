@id:9303
Feature: Busy blocks gathered from every enabled calendar
  A visitor sees the owner as busy whichever calendar holds the event,
  so a family event blocks a work booking as well.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the configuration enables several of the owner's calendars

  Scenario: An event in the calendar 'family' shows as busy
    Given the owner's calendar 'family' holds an event on 5 November 2026 from 17:00 to 18:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 17:00 to 18:00 UTC on 5 November 2026

  Scenario: Events in two calendars at the same time show as one busy block
    Given the owner's calendar 'work' holds an event on 5 November 2026 from 09:00 to 10:00 UTC
    And the owner's calendar 'sport' holds an event on 5 November 2026 from 09:00 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:00 UTC on 5 November 2026
