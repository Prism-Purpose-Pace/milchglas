@id:9309
Feature: Declined invitations free the owner
  A visitor can book a time the owner has declined,
  because a declined invitation is no busy time.

  Scenario: An invitation the owner declined leaves no busy block
    Given the owner's calendar 'work' holds an invitation on 9 November 2026 from 13:00 to 14:00 UTC
    And the owner declined that invitation
    When the refresh run finishes
    Then the feed lists no busy block on 9 November 2026

  Scenario: Only the accepted invitation of the day shows as busy
    Given the owner's calendar 'work' holds an accepted invitation on 9 November 2026 from 15:00 to 16:00 UTC
    And it holds a few declined invitations on 9 November 2026
    When the refresh run finishes
    Then the feed lists only the busy block from 15:00 to 16:00 UTC on 9 November 2026
