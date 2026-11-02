@id:9311
Feature: Busy blocks keep the owner's local hours across summer time
  A visitor sees the owner busy at the local hours the owner planned,
  whether summer time is in force or not.

  Background:
    Given the owner's time zone is Europe/Berlin
    And today is 20 October 2026

  Scenario: An event in winter time keeps its local hours
    Given the owner's calendar 'work' holds an event on 2 November 2026 from 09:00 to 10:00 Europe/Berlin time
    When the refresh run finishes
    Then the feed lists one busy block from 08:00 to 09:00 UTC on 2 November 2026

  Scenario: An event in summer time keeps its local hours
    Given the owner's calendar 'work' holds an event on a day with summer time from 09:00 to 10:00 Europe/Berlin time
    When the refresh run finishes
    Then the feed lists one busy block from 07:00 to 08:00 UTC
