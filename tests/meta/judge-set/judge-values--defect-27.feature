@id:9327
Feature: Events someone else enters still block the owner
  A visitor cannot book the owner into an event the owner's assistant entered,
  because the feed counts every event in the owner's calendars.

  Scenario: An event the assistant entered shows as busy
    Given the owner's assistant may write to the owner's calendar 'work'
    And the assistant Wenna Pruitt enters an event on 27 November 2026 from 08:00 to 09:30 UTC into that calendar
    When the refresh run finishes
    Then the feed lists one busy block from 08:00 to 09:30 UTC on 27 November 2026

  Scenario: An event the assistant cancelled leaves no busy block
    Given the owner's assistant may write to the owner's calendar 'work'
    And the calendar 'work' holds an event on 27 November 2026 from 11:00 to 12:00 UTC that the assistant cancelled
    When the refresh run finishes
    Then the feed lists no busy block on 27 November 2026
