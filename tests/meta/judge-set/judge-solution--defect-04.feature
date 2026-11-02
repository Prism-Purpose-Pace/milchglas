@id:9104
Feature: Weekly event across the window
  The owner's booking page shows every Monday of a weekly event as busy, not just the first.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: An event every Monday shows on each Monday in the window
    Given the window runs from 2 November 2026 to 5 December 2026
    And calendar 'work' holds an event every Monday from 10:00 to 11:00, first on 2 November 2026
    When a refresh run completes
    Then the feed, written with the icalendar library, lists 5 busy blocks from 10:00 to 11:00, one on each Monday from 2 to 30 November 2026
