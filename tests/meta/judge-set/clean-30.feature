@id:9530
Feature: End a one-day duration at the same local hour across the summer time switch
  A booking page sees the owner busy until the local hour the event really
  ends, even across the night summer time ends.

  Background:
    Given today is 20 October 2026 in Europe/Berlin

  Scenario: A one-day event from 09:00 on 24 October ends at 09:00 on 25 October
    Summer time ends in the night between the two days, so the event lasts 25 hours.

    Given calendar 'work' holds an event starting at 09:00 on 24 October 2026 with the duration P1D
    When a refresh run completes
    Then the feed lists one busy block from 09:00 on 24 October 2026 to 09:00 on 25 October 2026
    And its end line reads "DTEND:20261025T080000Z"
