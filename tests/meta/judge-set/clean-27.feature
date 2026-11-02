@id:9527
Feature: Health check follows the refresh runs through an outage
  The operator's monitor sees an outage of the calendar server once the feed
  is an hour old, and sees it end with the first successful refresh run.

  Background:
    Given the last successful refresh run ended at 09:00 on 28 October 2026
    And the calendar server refused every connection from 09:05 to 10:25 on that day

  Scenario: 65 minutes after the last successful refresh run the health check answers 503
    When the monitor asks the health check at 10:05 on 28 October 2026
    Then the health check answers status 503

  Scenario: The first successful refresh run after the outage turns it back to 200
    Given the refresh run at 10:30 on 28 October 2026 succeeded
    When the monitor asks the health check at 10:31 on 28 October 2026
    Then the health check answers status 200
