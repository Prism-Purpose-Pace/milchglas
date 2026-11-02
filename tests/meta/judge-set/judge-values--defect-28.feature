@id:9328
Feature: A refresh run that cannot reach a calendar keeps the last good feed
  A visitor keeps seeing the owner's last known busy times when a calendar fails,
  and the operator learns which calendar failed.

  Scenario: An unreachable shared calendar is recorded as the last error
    Given Jorunn shares the calendar 'sport' with the owner read-only
    And the calendar 'sport' cannot be reached on 28 October 2026 at 10:00 UTC
    When the refresh run finishes
    Then the last error names the calendar 'sport' as unreachable

  Scenario: An unreachable calendar leaves the last good feed in place
    Given the last good feed of 28 October 2026 at 09:45 UTC lists one busy block from 14:00 to 15:00 UTC on 2 November 2026
    And the calendar 'work' cannot be reached on 28 October 2026 at 10:00 UTC
    When the refresh run finishes
    Then the feed still lists one busy block from 14:00 to 15:00 UTC on 2 November 2026
