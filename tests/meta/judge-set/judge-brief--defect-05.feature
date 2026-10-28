@id:9405
Feature: Health check tells the operator whether the feed is fresh
  The operator learns that the feed has gone stale
  before a visitor books the owner into a time that is no longer free.

  Scenario: A feed refreshed 20 minutes ago is fresh
    Given the last refresh run succeeded at 09:40 UTC on 28 October 2026
    And the owner's calendar 'work' holds an event on 6 November 2026 from 14:00 to 15:00 UTC
    When the operator asks the health check at 10:00 UTC on 28 October 2026
    Then the health check reports the feed as fresh
    And the feed lists one busy block from 14:00 to 15:00 UTC on 6 November 2026

  Scenario: A feed refreshed 75 minutes ago is stale
    Given the last refresh run succeeded at 08:45 UTC on 28 October 2026
    When the operator asks the health check at 10:00 UTC on 28 October 2026
    Then the health check reports the feed as stale
