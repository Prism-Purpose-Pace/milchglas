@id:9206
Feature: Event the owner said no to
  The owner's booking page offers the time again once the owner has declined an event.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: An event declined by the owner leaves no busy block
    Given calendar user 1042 invited the owner to an event on 23 November 2026 from 16:00 to 17:00
    And the owner declined that event
    When a refresh run completes
    Then the feed lists no busy block on 23 November 2026
    But the declined event is still known to Milchglas
