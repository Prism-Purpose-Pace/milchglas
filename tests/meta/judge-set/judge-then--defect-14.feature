@id:9214
Feature: Every Wednesday of a weekly event
  The owner's booking page shows each Wednesday of a weekly event in the window as busy.

  Scenario: An event every Wednesday from 07:30 to 08:30 in the window
    Given the owner's time zone is Europe/Berlin
    And the window runs from 2 November 2026 to 5 December 2026
    And calendar 'sport' holds an event every Wednesday from 07:30 to 08:30, first on 4 November 2026
    When a refresh run completes
    Then Milchglas holds 5 instances of the weekly event
