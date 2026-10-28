@id:9307
Feature: Health check warns the operator of a feed left stale
  The operator learns that the feed has gone stale before a visitor
  books the owner into a time that is no longer free.

  Scenario: A feed refreshed 20 minutes ago is fresh
    Given the last refresh run succeeded at 09:40 UTC on 28 October 2026
    And the time is 10:00 UTC on 28 October 2026
    When the operator asks the health check
    Then the health check reports the feed as fresh

  Scenario: A feed not refreshed for a long time is stale
    Given the last refresh run succeeded a while ago
    When the operator asks the health check
    Then the health check reports the feed as stale
