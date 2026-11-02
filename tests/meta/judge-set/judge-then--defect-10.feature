@id:9210
Feature: Health check watches the age of the feed
  The operator learns from the health check alone that the feed has stopped updating.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: A feed written 20 minutes ago keeps the health check at 200
    Given the last good feed was written at 08:00 on 4 November 2026
    When the health check is asked at 08:20 on 4 November 2026
    Then the health check answers 200

  Scenario: A feed written 90 minutes ago is reported as stale
    Given the last good feed was written at 08:00 on 4 November 2026
    When the health check is asked at 09:30 on 4 November 2026
    Then the refresher sets its stale flag
