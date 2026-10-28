@id:9217
Feature: Half-hour grid for an afternoon event
  The owner's booking page offers whole half hours around an event that does not fit the grid.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the grid is 30 minutes

  Scenario: An event from 16:20 to 16:50 is rounded out to the grid
    Given calendar 'work' holds an event on 18 November 2026 from 16:20 to 16:50
    When a refresh run completes
    Then the rounded start is kept as 16:00 inside Milchglas

  Scenario: An event from 16:00 to 16:30 already on the grid keeps its times
    Given calendar 'work' holds an event on 18 November 2026 from 16:00 to 16:30
    When a refresh run completes
    Then the feed lists one busy block on 18 November 2026 from 16:00 to 16:30
