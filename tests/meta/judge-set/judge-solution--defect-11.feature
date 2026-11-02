@id:9111
Feature: Summer time ends inside the window
  The owner's booking page shows an evening event at the right hour on both sides of the clock change.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the refresher converts every time with the dateutil library

  Scenario: An event the day before the clock change keeps its local hour
    Given calendar 'work' holds an event on 24 October 2026 from 18:00 to 19:00
    When a refresh run completes
    Then the feed lists one busy block on 24 October 2026 from 16:00 to 17:00 UTC

  Scenario: An event the day after the clock change keeps its local hour
    Given calendar 'work' holds an event on 26 October 2026 from 18:00 to 19:00
    When a refresh run completes
    Then the feed lists one busy block on 26 October 2026 from 17:00 to 18:00 UTC
