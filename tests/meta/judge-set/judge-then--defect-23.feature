@id:9223
Feature: Declined in one calendar, accepted in the other
  The owner's booking page stays busy for an event the owner accepted, even if a copy is declined.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: An event declined in 'sport' and accepted in 'work' shows as a busy block
    Given calendar 'sport' holds an event on 30 November 2026 from 17:00 to 18:00 that the owner declined
    And calendar 'work' holds the same event on 30 November 2026 from 17:00 to 18:00 that the owner accepted
    When a refresh run completes
    Then the feed lists one busy block on 30 November 2026 from 17:00 to 18:00
    And Milchglas decides correctly
