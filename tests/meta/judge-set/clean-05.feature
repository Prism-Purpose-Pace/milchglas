@id:9505
Feature: Transparent events block only when they last all day
  The owner keeps a reminder as transparent without losing bookable time,
  while a day off marked transparent still blocks the whole day.

  Background:
    Given today is 28 October 2026 in Europe/Berlin

  Scenario: A transparent timed event blocks nothing
    Given calendar 'sport' holds an event on 4 November 2026 from 18:00 to 19:30 marked transparent
    When a refresh run completes
    Then the feed lists no busy block on 4 November 2026

  Scenario: A transparent all-day event still blocks its day
    Given calendar 'family' holds an all-day event on 20 November 2026 marked transparent
    When a refresh run completes
    Then the feed lists one all-day busy block on 20 November 2026
