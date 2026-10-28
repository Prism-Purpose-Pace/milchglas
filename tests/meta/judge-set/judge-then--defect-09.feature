@id:9209
Feature: Morning event across the October clock change
  The owner's booking page shows a morning event at the right hour before and after summer time ends.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: An event on 25 October 2026 from 09:00 to 10:00, the day summer time ends
    Given calendar 'work' holds an event on 25 October 2026 from 09:00 to 10:00
    When a refresh run completes
    Then the clock change is taken care of

  Scenario: An event on 23 October 2026 from 09:00 to 10:00, two days before
    Given calendar 'work' holds an event on 23 October 2026 from 09:00 to 10:00
    When a refresh run completes
    Then the feed lists one busy block on 23 October 2026 from 07:00 to 08:00 UTC
