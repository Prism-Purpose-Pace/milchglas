@id:9503
Feature: Leave cancelled events out of the feed
  The owner gets the time of a cancelled event back as bookable time.

  Background:
    Given today is 28 October 2026 in Europe/Berlin

  Scenario: Only the event still taking place blocks the afternoon
    Given calendar 'family' holds 2 events on 5 November 2026
    And the event from 14:00 to 15:00 is cancelled and the one from 16:00 to 17:00 is confirmed
    When a refresh run completes
    Then the feed lists one busy block on 5 November 2026 from 16:00 to 17:00
    But the feed lists no busy block from 14:00 to 15:00 on that day

  Scenario: A cancelled instance of a recurring event frees only its own evening
    Given calendar 'sport' holds a recurring event every Thursday from 19:00 to 20:30 starting 5 November 2026
    And its instance on 12 November 2026 is cancelled
    When a refresh run completes
    Then the feed lists busy blocks from 19:00 to 20:30 on 5, 19 and 26 November 2026
    And the feed lists no busy block on 12 November 2026
