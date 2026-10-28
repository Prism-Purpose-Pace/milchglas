@id:9130
Feature: One unreachable calendar fails the whole refresh run
  The booking page never shows a half-read week: when one calendar fails, the last good feed stays.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the configuration lists calendar 'work' and calendar 'sport' as enabled

  Scenario: An unreachable calendar 'sport' keeps the last good feed
    Given the last good feed lists one busy block on 3 November 2026 from 09:00 to 10:00
    And the server for calendar 'sport' refuses every connection
    When a refresh run ends
    Then the feed still lists one busy block on 3 November 2026 from 09:00 to 10:00

  Scenario: An unreachable calendar 'sport' is named in the last error
    Given the client sends 2 requests to calendar 'work' before it tries calendar 'sport'
    And the server for calendar 'sport' refuses every connection
    When a refresh run ends
    Then the last error names calendar 'sport' as unreachable
