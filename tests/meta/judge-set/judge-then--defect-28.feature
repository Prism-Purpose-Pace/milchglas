@id:9228
Feature: Tentative and cancelled events on one Thursday
  The owner's booking page stays busy for a tentative event and frees the time of a cancelled one.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: A tentative event from 11:00 to 12:00 on 3 December 2026
    Given calendar 'work' holds a tentative event on 3 December 2026 from 11:00 to 12:00
    When a refresh run completes
    Then the tentative event is flagged busy inside Milchglas

  Scenario: A cancelled event from 14:00 to 15:00 on 3 December 2026
    Given calendar 'work' holds a cancelled event on 3 December 2026 from 14:00 to 15:00
    When a refresh run completes
    Then the feed lists no busy block on 3 December 2026 from 14:00 to 15:00
