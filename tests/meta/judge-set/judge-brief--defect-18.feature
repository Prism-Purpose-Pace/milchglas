@id:9418
Feature: Health check reports whether the feed is up to date
  The operator learns within an hour that the refresh runs have stopped,
  so a stale feed does not go unnoticed.

  Scenario: A feed refreshed 30 minutes ago is fresh
    Given the last refresh run succeeded at 09:30 UTC on 28 October 2026
    When the operator asks the health check at 10:00 UTC on 28 October 2026
    Then the health check reports the feed as fresh

  Scenario: An invitation the owner declined leaves no busy block
    Given the owner's calendar 'work' holds an invitation on 18 November 2026 from 10:00 to 11:00 UTC that the owner declined
    When the refresh run finishes
    Then the feed lists no busy block on 18 November 2026

  Scenario: A feed refreshed 90 minutes ago is stale
    Given the last refresh run succeeded at 08:30 UTC on 28 October 2026
    When the operator asks the health check at 10:00 UTC on 28 October 2026
    Then the health check reports the feed as stale
