@id:9426
Feature: The feed carries the configured summary on every busy block
  The owner decides what a visitor reads on each busy block,
  so the booking page shows the owner's words and never an event title.

  Scenario: The default summary appears on a busy block
    Given the owner's calendar 'work' holds an event on 26 November 2026 from 09:00 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:00 UTC with the summary 'Blocker Privat'

  Scenario: A configured summary replaces the default
    Given the configured summary is 'Not available'
    And the owner's calendar 'work' holds an event on 26 November 2026 from 09:00 to 10:00 UTC
    When the refresh run finishes
    Then the export lists one busy block from 09:00 to 10:00 UTC with the summary 'Not available'
