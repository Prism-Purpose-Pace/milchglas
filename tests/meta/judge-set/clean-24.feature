@id:9524
Feature: Write timed busy blocks in UTC
  Every subscribed calendar app places a busy block at the right hour,
  whatever time zone it runs in.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: A local morning hour in November is written one hour earlier in UTC
    Given calendar 'work' holds an event on 2 November 2026 from 09:00 to 10:00 local time
    When a refresh run completes on 28 October 2026
    Then the feed holds the line "DTSTART:20261102T080000Z"
    And it holds the line "DTEND:20261102T090000Z"
    But it holds no VTIMEZONE section
