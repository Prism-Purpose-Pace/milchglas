@id:9222
Feature: Same UID for an unchanged busy block
  The booking page recognises a busy block from the last refresh run and does not show it twice.

  Scenario: Two refresh runs over an unchanged event on 26 November 2026
    Given the owner's time zone is Europe/Berlin
    And calendar 'work' holds an event on 26 November 2026 from 15:00 to 16:00
    And a refresh run at 10:00 on 3 November 2026 wrote the feed
    When the next refresh run at 10:15 on 3 November 2026 completes
    Then the UID of the busy block is kept in the refresher between the two runs
