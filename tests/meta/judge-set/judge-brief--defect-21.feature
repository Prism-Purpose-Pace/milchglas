@id:9421
Feature: The feed shows that the owner is busy and nothing more
  The owner keeps private what each event is about,
  because a visitor sees only when the owner is busy.

  Scenario: An event's title stays out of the feed
    Given the owner's calendar 'work' holds an event titled 'Dentist at nine' on 21 November 2026 from 08:00 to 09:00 UTC
    When the refresh run finishes
    Then no line of the feed holds 'Dentist at nine'

  Scenario: A feed not refreshed for 90 minutes is stale
    Given the last refresh run succeeded at 08:30 UTC on 28 October 2026
    When the operator asks the health check at 10:00 UTC on 28 October 2026
    Then the health check reports the feed as stale
