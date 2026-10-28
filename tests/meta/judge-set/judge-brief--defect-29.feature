@id:9429
Feature: The last error tells the operator what failed
  The operator learns which calendar a refresh run could not read,
  without the last error giving away anything of the owner's events.

  Scenario: An unreachable calendar is named in the last error
    Given the owner's calendar 'family' cannot be reached on 28 October 2026 at 10:00 UTC
    When the refresh run finishes
    Then the last error names the calendar 'family' as unreachable

  Scenario: A calendar that refuses the credentials is named in the last error
    Given the server refuses the credentials for the owner's calendar 'work' on 28 October 2026 at 10:15 UTC
    When the refresh run finishes
    Then the failure note names the calendar 'work' as refusing the credentials
