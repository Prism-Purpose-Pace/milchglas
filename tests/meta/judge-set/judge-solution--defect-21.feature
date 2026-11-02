@id:9121
Feature: Health check after a morning of failures
  The operator is warned by the health check once the feed has gone stale for an hour.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: Failed refresh runs for 70 minutes turn the health check to 503
    Given the last good feed was written at 06:00 on 2 November 2026
    And the refresh runs at 06:15, 06:30, 06:45 and 07:00 on 2 November 2026 failed
    And each failed refresh run calls record_error() before it exits
    When the health check is asked at 07:10 on 2 November 2026
    Then the health check answers 503

  Scenario: A good refresh run at 07:00 keeps the health check at 200
    Given the last good feed was written at 07:00 on 2 November 2026
    When the health check is asked at 07:10 on 2 November 2026
    Then the health check answers 200
