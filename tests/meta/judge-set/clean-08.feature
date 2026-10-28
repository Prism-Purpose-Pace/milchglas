@id:9508
Feature: Show busy blocks only inside the 33 day window
  A booking page that looks 30 days ahead finds every busy block it needs
  inside the window.

  Background:
    Given today is 28 October 2026 in Europe/Berlin
    And the window is 33 days

  Scenario: The last day of the window still shows its event
    Given calendar 'work' holds an event on 29 November 2026 from 09:00 to 10:00
    When a refresh run completes
    Then the feed lists one busy block on 29 November 2026 from 09:00 to 10:00

  Scenario: An event across the end of the window is cut at midnight
    Given calendar 'family' holds an event from 23:00 on 29 November 2026 to 01:00 on 30 November 2026
    When a refresh run completes
    Then the feed lists one busy block from 23:00 on 29 November 2026 to 00:00 on 30 November 2026
    And the feed lists no busy block after 00:00 on 30 November 2026
