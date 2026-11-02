@id:9406
Feature: An invitation the owner declined frees the time
  A visitor can book a time the owner has declined,
  because a declined invitation is no busy time.

  Scenario: An accepted invitation shows as busy
    Given the owner's calendar 'work' holds an invitation on 9 November 2026 from 15:00 to 16:00 UTC that the owner accepted
    When the refresh run finishes
    Then the feed lists one busy block from 15:00 to 16:00 UTC on 9 November 2026

  Scenario: A declined invitation leaves no busy block
    Given the owner's calendar 'work' holds an invitation on 9 November 2026 from 13:00 to 14:00 UTC that the owner declined
    When the refresh run finishes at 10:00 UTC on 28 October 2026
    Then the feed lists no busy block on 9 November 2026
    And the health check shows 10:00 UTC on 28 October 2026 as the time of the last success
