@id:9305
Feature: Every instance of a weekly event blocks the owner
  A visitor cannot book the owner during any instance of a weekly event,
  not only during the first one.

  Background:
    Given today is 28 October 2026 in Europe/Berlin

  Scenario: A weekly event shows one busy block per week
    Given the owner's calendar 'sport' holds a weekly event on Tuesdays from 18:00 to 19:00 UTC from 3 November 2026 to 24 November 2026
    When the refresh run finishes
    Then the feed lists busy blocks from 18:00 to 19:00 UTC on 3, 10, 17 and 24 November 2026

  Scenario: Instances after the window leave no busy block
    Given the owner's calendar 'sport' holds a weekly event on Tuesdays from 18:00 to 19:00 UTC starting on 3 November 2026
    And the event goes on for many more weeks
    When the refresh run finishes
    Then the feed lists no busy block after 30 November 2026
