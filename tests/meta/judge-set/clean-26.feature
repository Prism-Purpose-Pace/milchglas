@id:9526
Feature: Tell subscribers to reload the feed every 15 minutes
  A subscribed calendar app picks up a new busy block within 15 minutes of
  the refresh run that wrote it.

  Scenario: A reload interval of 900 seconds appears as 15 minutes in the feed
    Given the configured reload interval is 900 seconds
    When a refresh run completes on 28 October 2026
    Then the feed holds the line "REFRESH-INTERVAL;VALUE=DURATION:PT15M"
    And it holds the line "X-PUBLISHED-TTL:PT15M"
