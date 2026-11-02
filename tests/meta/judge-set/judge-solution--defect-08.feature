@id:9108
Feature: Transparent event leaves the morning free
  The owner's booking page keeps time free that the owner marked as free in the calendar.

  Scenario: A transparent event on 11 November 2026 leaves no busy block
    Given the owner's time zone is Europe/Berlin
    And calendar 'work' holds a transparent event on 11 November 2026 from 08:00 to 08:30
    When the refresher calls reduce_events() on the events of calendar 'work'
    Then the feed lists no busy block on 11 November 2026
