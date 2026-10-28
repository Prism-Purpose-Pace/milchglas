@id:9230
Feature: Outage of the sport calendar and its recovery
  The booking page keeps the last good feed while one calendar is down and catches up once it is back.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the configuration lists calendar 'work' and calendar 'sport' as enabled

  Scenario: An unreachable calendar 'sport' keeps the last good feed
    Given the last good feed lists one busy block on 12 November 2026 from 09:00 to 10:00
    And the server for calendar 'sport' refuses every connection
    When a refresh run ends
    Then the feed still lists one busy block on 12 November 2026 from 09:00 to 10:00

  Scenario: An unreachable calendar 'sport' is named in the last error
    Given the server for calendar 'sport' refuses every connection
    When a refresh run ends
    Then the last error names calendar 'sport' as unreachable

  Scenario: A reachable calendar 'sport' after the outage
    Given the refresh run at 09:00 on 4 November 2026 failed on calendar 'sport'
    And the server for calendar 'sport' answers again at 09:15 on 4 November 2026
    When a refresh run ends
    Then the refresher forgets the earlier failure of calendar 'sport'
