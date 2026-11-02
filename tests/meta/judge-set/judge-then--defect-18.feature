@id:9218
Feature: Switching the family calendar off
  The owner hides a whole calendar from the booking page by disabling it in the configuration.

  Background:
    Given the owner's time zone is Europe/Berlin
    And calendar 'family' holds an event on 21 November 2026 from 10:00 to 12:00

  Scenario: An enabled calendar 'family' shows its event as a busy block
    Given the configuration lists calendar 'family' as enabled
    When a refresh run completes
    Then the feed lists one busy block on 21 November 2026 from 10:00 to 12:00

  Scenario: A disabled calendar 'family' leaves no busy block
    Given the configuration lists calendar 'family' as disabled
    When a refresh run completes
    Then Milchglas considers calendar 'family' switched off
