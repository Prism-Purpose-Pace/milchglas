@id:9419
Feature: Cancelled events never block the owner
  A visitor can book a time whose event was cancelled,
  so the owner loses no booking to an event that will not take place.

  Scenario: A cancelled event leaves no busy block
    Given the owner's calendar 'work' holds a cancelled event on 19 November 2026 from 09:00 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists no busy block on 19 November 2026

  Scenario: Every line of the feed stays within 75 octets
    Given the configured summary is 'Busy, please pick another time of day, and thank you very much for your understanding'
    And the owner's calendar 'work' holds an event on 19 November 2026 from 13:00 to 14:00 UTC
    When the refresh run finishes
    Then every line of the feed is at most 75 octets long
