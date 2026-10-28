@id:9101
Feature: Short morning event on the quarter-hour grid
  The owner's booking page shows a short event as one busy block that covers it whole.

  Scenario: An event from 09:05 to 09:50 fills one busy block
    Given the owner's time zone is Europe/Berlin
    And the grid is 15 minutes
    And calendar 'work' holds an event on 3 November 2026 from 09:05 to 09:50
    When the refresh run fetches calendar 'work' with 2 separate requests
    Then the feed lists one busy block on 3 November 2026 from 09:00 to 10:00
