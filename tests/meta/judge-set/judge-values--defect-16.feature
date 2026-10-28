@id:9316
Feature: Transparent events leave the owner free
  A visitor can book a time the owner marked as free in the calendar,
  so an event marked as free costs the owner no booking.

  Background:
    Given the configuration enables only the owner's calendar 'test'

  Scenario: A transparent timed event leaves no busy block
    Given that calendar holds a transparent event on 16 November 2026 from 08:00 to 09:00 UTC
    When the refresh run finishes
    Then the feed lists no busy block on 16 November 2026

  Scenario: An opaque timed event shows as busy
    Given that calendar holds an opaque event on 16 November 2026 from 10:00 to 11:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 10:00 to 11:00 UTC on 16 November 2026
