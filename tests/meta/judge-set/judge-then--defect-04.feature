@id:9204
Feature: Unconfirmed event stays busy
  The owner's booking page keeps an event the owner has not yet confirmed off limits for others.

  Scenario: A tentative event on 6 November 2026 from 14:00 to 14:30
    Given the owner's time zone is Europe/Berlin
    And calendar 'work' holds a tentative event on 6 November 2026 from 14:00 to 14:30
    When a refresh run completes
    Then Milchglas knows the event is tentative
