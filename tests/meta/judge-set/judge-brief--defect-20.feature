@id:9420
Feature: A failed refresh run keeps the last good feed
  A visitor keeps seeing the owner's last known busy times when a calendar cannot be reached,
  instead of a feed that shows the owner as free.

  Scenario: An unreachable calendar leaves the last good feed in place
    Given the last good feed lists one busy block from 14:00 to 15:00 UTC on 2 November 2026
    And the owner's calendar 'work' cannot be reached
    When the refresh run finishes
    Then the feed still lists one busy block from 14:00 to 15:00 UTC on 2 November 2026

  Scenario: An event after the end of summer time keeps its local hours
    Given the owner's time zone is Europe/Berlin
    And today is 20 October 2026
    And the owner's calendar 'work' holds an event on 26 October 2026 from 09:00 to 10:00 Europe/Berlin time
    When the refresh run finishes
    Then the feed lists one busy block from 08:00 to 09:00 UTC on 26 October 2026

  Scenario: An unreachable calendar is recorded as the last error
    Given the owner's calendar 'family' cannot be reached
    When the refresh run finishes
    Then the last error names the calendar 'family' as unreachable
