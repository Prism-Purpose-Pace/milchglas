@id:9110
Feature: Health check on a feed past its hour
  The operator sees from the health check alone whether the feed is fresh enough to trust.

  Scenario: A feed 45 minutes old keeps the health check at 200
    Given the last good feed was written at 06:00 on 2 November 2026 Europe/Berlin
    When the health check is asked at 06:45 on 2 November 2026 Europe/Berlin
    Then the health check answers 200

  Scenario: A feed 61 minutes old turns the health check to 503 even with a warm cache
    Given the last good feed was written at 06:00 on 2 November 2026 Europe/Berlin
    When the health check is asked at 07:01 on 2 November 2026 Europe/Berlin
    Then the health check answers 503
