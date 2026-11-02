@id:9117
Feature: Thirty-minute grid for a late event
  The owner's booking page leaves no unusable sliver after an event that ends off the grid.

  Scenario: An event from 16:10 to 16:40 becomes a busy block from 16:00 to 17:00
    Given the owner's time zone is Europe/Berlin
    And the grid is 30 minutes
    And calendar 'work' holds an event on 17 November 2026 from 16:10 to 16:40
    When the refresher runs a calendar-query with expand for calendar 'work'
    Then the feed lists one busy block on 17 November 2026 from 16:00 to 17:00
