@id:9107
Feature: Tentative event still counts against bookings
  The owner's booking page treats an event the owner may attend as busy, so nobody books over it.

  Scenario: A tentative event on 10 November 2026 shows as one busy block
    Given the owner's time zone is Europe/Berlin
    And calendar 'work' holds a tentative event on 10 November 2026 from 15:00 to 16:00
    And the refresher keeps the events of calendar 'work' in a hash map keyed by start time
    When a refresh run completes
    Then the feed lists one busy block on 10 November 2026 from 15:00 to 16:00
