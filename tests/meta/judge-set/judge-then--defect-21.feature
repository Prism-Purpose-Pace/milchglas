@id:9221
Feature: Health check after a night without a good refresh run
  The operator notices from the health check that the feed has not been refreshed for hours.

  Scenario: The last good feed is from 23:00 and the health check is asked at 02:00
    Given the owner's time zone is Europe/Berlin
    And the last good feed was written at 23:00 on 8 November 2026
    When the health check is asked at 02:00 on 9 November 2026
    Then the operator gets the right signal
