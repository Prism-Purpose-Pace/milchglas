@id:9128
Feature: Tentative and cancelled in one week
  The owner's booking page keeps a tentative event as busy and frees a cancelled one.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the refresher asks the server with one REPORT query per calendar at depth 1

  Scenario: A tentative event shows as a busy block
    Given calendar 'work' holds a tentative event on 26 November 2026 from 10:00 to 11:00
    When a refresh run completes
    Then the feed lists one busy block on 26 November 2026 from 10:00 to 11:00

  Scenario: A cancelled event leaves no busy block
    Given calendar 'work' holds a cancelled event on 27 November 2026 from 10:00 to 11:00
    When a refresh run completes
    Then the feed lists no busy block on 27 November 2026
