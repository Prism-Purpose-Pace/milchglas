@id:9325
Feature: Only the owner's own answer frees an invitation
  A visitor can book a time only when the owner has declined it,
  so another attendee's answer never opens the owner's time.

  Scenario: An invitation the owner declined leaves no busy block
    Given the owner's calendar 'work' holds an invitation on 25 November 2026 from 10:00 to 11:00 UTC
    And the owner declined that invitation
    When the refresh run finishes
    Then the feed lists no busy block on 25 November 2026

  Scenario: An invitation another attendee declined stays busy
    Given the owner's calendar 'work' holds an invitation on 25 November 2026 from 13:00 to 14:00 UTC that the owner accepted
    And Greta Lindqvarn declined the same invitation
    When the refresh run finishes
    Then the feed lists one busy block from 13:00 to 14:00 UTC on 25 November 2026
