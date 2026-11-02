@id:9308
Feature: Events far ahead stay out of the feed
  A visitor can book the owner on days beyond the window,
  because the feed lists busy blocks only for the coming 33 days.

  Background:
    Given today is 28 October 2026 in Europe/Berlin

  Scenario: An event on 12 November 2026 shows as busy
    Given the owner's calendar 'work' holds an event on 12 November 2026 from 14:00 to 15:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 14:00 to 15:00 UTC on 12 November 2026

  Scenario: An event months ahead leaves no busy block
    Given the owner's calendar 'work' holds an event far in the future
    When the refresh run finishes
    Then the feed lists no busy block
