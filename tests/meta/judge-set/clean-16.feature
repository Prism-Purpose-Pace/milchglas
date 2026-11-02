@id:9516
Feature: Block whole days for all-day events
  A booking page offers no time on a day the owner marked as taken for the
  whole day.

  Background:
    Given today is 28 October 2026 in Europe/Berlin

  Scenario: A one-day event gives an all-day busy block on its date
    Given calendar 'family' holds an all-day event on 20 November 2026
    When a refresh run completes
    Then the feed lists one all-day busy block on 20 November 2026
    And its start line reads "DTSTART;VALUE=DATE:20261120"

  Scenario: A three-day event gives one all-day busy block over all three days
    Given calendar 'family' holds an all-day event from 21 November 2026 to 23 November 2026 inclusive
    When a refresh run completes
    Then the feed lists one all-day busy block covering 21, 22 and 23 November 2026
    And its end line reads "DTEND;VALUE=DATE:20261124"
