@id:9114
Feature: Last good feed survives a server outage
  The booking page keeps showing the owner's busy times while the calendar server is down.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the last good feed lists one busy block on 3 November 2026 from 09:00 to 10:00

  Scenario: A failed refresh run keeps the last good feed
    Given the server for calendar 'work' answers 503 to every request
    When the refresh run gives up on calendar 'work' after 3 retries with backoff
    Then the feed still lists one busy block on 3 November 2026 from 09:00 to 10:00

  Scenario: A failed refresh run records the last error
    Given the server for calendar 'work' answers 503 to every request
    When a refresh run ends
    Then the last error names calendar 'work' and the answer 503
