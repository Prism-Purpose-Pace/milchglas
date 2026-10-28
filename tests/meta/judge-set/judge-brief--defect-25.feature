@id:9425
Feature: Tentative events count as busy
  A visitor cannot book the owner into a time the owner has kept open,
  because a tentative event counts as busy like a confirmed one.

  Scenario: A tentative event shows as busy
    Given the owner's calendar 'work' holds a confirmed event on 25 November 2026 from 08:00 to 09:00 UTC
    And it holds a tentative appointment on 25 November 2026 from 10:00 to 11:00 UTC
    When the refresh run finishes
    Then the feed lists busy blocks from 08:00 to 09:00 UTC and from 10:00 to 11:00 UTC on 25 November 2026

  Scenario: A tentative event next to a confirmed event becomes one busy block
    Given the owner's calendar 'work' holds a tentative event on 25 November 2026 from 13:00 to 14:00 UTC
    And it holds a confirmed event on 25 November 2026 from 14:00 to 15:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 13:00 to 15:00 UTC on 25 November 2026
