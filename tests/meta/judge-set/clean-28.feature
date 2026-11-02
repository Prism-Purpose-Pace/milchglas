@id:9528
Feature: Read the calendar that calendar user 1042 shares with the service user
  Calendar user 1042 shares the calendar 'sport' read-only once, and from then
  on its events show as busy blocks.

  Background:
    Given today is 28 October 2026 in Europe/Berlin
    And calendar user 1042 shares the calendar 'sport' read-only with the service user

  Scenario: An event in the shared calendar becomes a busy block
    Given calendar 'sport' holds an event on 7 November 2026 from 10:00 to 12:00
    When a refresh run completes
    Then the feed lists one busy block on 7 November 2026 from 10:00 to 12:00

  Scenario: The attendees of a shared event stay out of the feed
    Given calendar 'sport' holds an event on 8 November 2026 from 10:00 to 12:00 with calendar users 2077 and 3150 as attendees
    When a refresh run completes
    Then the feed holds no ATTENDEE line
