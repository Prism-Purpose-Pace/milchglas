@id:9509
Feature: Health check reports a feed older than 60 minutes as stale
  The operator's monitor learns within the hour that the feed stopped
  following the owner's calendars.

  Background:
    Given the configuration holds a feed token digest of 64 hex characters

  Scenario Outline: The health check turns at exactly 60 minutes
    Given the last successful refresh run ended at <ended> on 28 October 2026
    When the monitor asks the health check at 11:00 on 28 October 2026
    Then the health check answers status <status>
    And the answer has no body

    Examples:
      | ended | status |
      | 10:01 | 200    |
      | 10:00 | 503    |
