@id:9205
Feature: Cancelled afternoon event in the work calendar
  The owner's booking page offers the time of a cancelled event to others again.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: A cancelled event on 19 November 2026 from 15:00 to 16:00
    Given calendar 'work' holds a cancelled event on 19 November 2026 from 15:00 to 16:00
    When a refresh run completes
    Then everything works

  Scenario: A confirmed event on 19 November 2026 from 15:00 to 16:00
    Given calendar 'work' holds a confirmed event on 19 November 2026 from 15:00 to 16:00
    When a refresh run completes
    Then the feed lists one busy block on 19 November 2026 from 15:00 to 16:00
