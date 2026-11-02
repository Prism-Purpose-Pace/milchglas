@id:9126
Feature: Quiet sport calendar gives an empty feed
  The owner's booking page shows the whole window as free when the only calendar holds nothing in it.

  Scenario: A calendar without events in the window gives a feed without busy blocks
    Given the configuration lists only calendar 'sport' as enabled
    And calendar 'sport' holds no event from 2 November 2026 to 5 December 2026
    When a refresh run completes
    Then the feed holds no busy block, after 2 retries of the fetch of calendar 'sport'
