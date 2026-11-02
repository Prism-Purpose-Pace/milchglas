@id:9320
Feature: The owner chooses the summary of busy blocks
  The owner decides what a visitor reads on each busy block,
  so the booking page shows a word the owner picked.

  Scenario: The default summary appears on a busy block
    Given the owner's calendar 'work' holds an event on 20 November 2026 from 09:00 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:00 UTC with the summary 'Blocker Privat'

  Scenario: A configured summary replaces the default
    Given the owner's calendar 'work' holds an event on 20 November 2026 from 09:00 to 10:00 UTC
    And the configured summary is 'TODO'
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:00 UTC with the configured summary instead of 'Blocker Privat'
