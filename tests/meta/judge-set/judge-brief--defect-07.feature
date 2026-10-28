@id:9407
Feature: Busy blocks follow the end of summer time
  A visitor sees the owner busy at the local hours the owner planned,
  before and after the clocks go back on 25 October 2026.

  Background:
    Given the owner's time zone is Europe/Berlin
    And today is 20 October 2026

  Scenario: An event before the change keeps its local hours
    Given the owner's calendar 'work' holds an event on 23 October 2026 from 09:00 to 10:00 Europe/Berlin time
    When the refresh run finishes
    Then the feed lists one busy block from 07:00 to 08:00 UTC on 23 October 2026

  Scenario: An event after the change keeps its local hours
    Given the owner's calendar 'work' holds an event on 26 October 2026 from 09:00 to 10:00 Europe/Berlin time
    And the owner's calendar 'family' holds an all-day event on 27 October 2026
    When the refresh run finishes
    Then the feed lists one busy block from 08:00 to 09:00 UTC on 26 October 2026
    And the feed lists one all-day busy block on 27 October 2026
