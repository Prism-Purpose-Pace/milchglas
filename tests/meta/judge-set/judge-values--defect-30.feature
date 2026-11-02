@id:9330
Feature: Tentative events in a shared calendar count as busy
  A visitor cannot book the owner into a time the owner has kept open,
  because a tentative event counts as busy like a confirmed one.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the calendar 'family' belongs to Fenwick Dorralby and is shared with the owner read-only

  Scenario: A tentative event shows as busy
    Given the calendar 'family' holds a tentative event on 30 November 2026 from 15:00 to 16:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 15:00 to 16:00 UTC on 30 November 2026

  Scenario: A tentative and a confirmed event that overlap become one busy block
    Given the calendar 'family' holds a tentative event on 30 November 2026 from 15:00 to 16:00 UTC
    And it holds a confirmed event on 30 November 2026 from 15:30 to 17:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 15:00 to 17:00 UTC on 30 November 2026
