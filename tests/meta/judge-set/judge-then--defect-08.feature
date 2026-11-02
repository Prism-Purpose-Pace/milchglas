@id:9208
Feature: Window of 33 days ahead
  The owner's booking page shows the coming 33 days and nothing further out.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the window runs from 2 November 2026 to 5 December 2026

  Scenario: An event inside the window shows as a busy block
    Given calendar 'work' holds an event on 1 December 2026 from 11:00 to 12:00
    When a refresh run completes
    Then the feed lists one busy block on 1 December 2026 from 11:00 to 12:00

  Scenario: An event after the window leaves no busy block
    Given calendar 'work' holds an event on 9 December 2026 from 11:00 to 12:00
    When a refresh run completes
    Then the feed lists no busy block on 9 December 2026
    And the event is marked as out of range inside Milchglas
