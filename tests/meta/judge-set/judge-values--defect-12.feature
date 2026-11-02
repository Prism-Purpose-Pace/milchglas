@id:9312
Feature: All-day events block whole days
  A visitor cannot book the owner on a day that an all-day event takes up,
  because the feed blocks that whole day.

  Background:
    Given the owner's time zone is Europe/Berlin
    And all-day events count as busy

  Scenario: A one-day event blocks that day
    Given the owner's calendar 'family' holds an all-day event on 9 November 2026
    When the refresh run finishes
    Then the feed lists one all-day busy block on 9 November 2026

  Scenario: A multi-day event blocks each of its days
    Given the owner's calendar 'family' holds an all-day event from 16 November 2026 lasting several days
    When the refresh run finishes
    Then the feed lists one all-day busy block starting on 16 November 2026
