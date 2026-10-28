@id:9226
Feature: Sport calendar without events
  The owner's booking page shows the whole window as free when the enabled calendar holds no event.

  Scenario: Calendar 'sport' holds no event from 2 November 2026 to 5 December 2026
    Given the configuration lists only calendar 'sport' as enabled
    And calendar 'sport' holds no event from 2 November 2026 to 5 December 2026
    When a refresh run completes
    Then Milchglas finds nothing to do for calendar 'sport'
