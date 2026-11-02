@id:9513
Feature: Keep the published feed while the calendar server is unreachable
  A subscriber keeps seeing the owner's busy blocks from the last good run,
  and the operator reads which calendar failed.

  Background:
    Given a refresh run wrote the feed with 4 busy blocks at 09:45 on 28 October 2026
    And the calendar server refuses every connection for calendar 'work' since 09:50

  Scenario: The feed written at 09:45 stays as it was
    When the refresh run at 10:00 ends
    Then the feed is byte-identical to the one written at 09:45

  Scenario: The last error names the calendar that failed
    When the refresh run at 10:00 ends
    Then the last error names the calendar 'work' as unreachable
    And it gives 10:00 on 28 October 2026 as its time
