@id:9123
Feature: Declined copy beside an accepted copy
  The owner's booking page frees the time of a declined event, but not of one the owner
  accepted in another calendar.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the icalendar parser reads every event of calendar 'work' and calendar 'family' line by line

  Scenario: An event declined in 'family' alone leaves no busy block
    Given calendar 'family' holds an event on 20 November 2026 from 12:00 to 13:00 that the owner declined
    When a refresh run completes
    Then the feed lists no busy block on 20 November 2026

  Scenario: An event declined in 'family' and accepted in 'work' shows as a busy block
    Given calendar 'family' holds an event on 20 November 2026 from 12:00 to 13:00 that the owner declined
    And calendar 'work' holds the same event on 20 November 2026 from 12:00 to 13:00 that the owner accepted
    When a refresh run completes
    Then the feed lists one busy block on 20 November 2026 from 12:00 to 13:00
