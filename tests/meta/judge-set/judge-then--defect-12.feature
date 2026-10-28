@id:9212
Feature: Last good feed during a timeout
  The booking page keeps the owner's busy times while the calendar server does not answer.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the last good feed lists one busy block on 10 November 2026 from 13:00 to 14:00

  Scenario: A refresh run that times out keeps the last good feed
    Given the server for calendar 'work' lets every connection time out
    When a refresh run ends
    Then the feed still lists one busy block on 10 November 2026 from 13:00 to 14:00
    And the refresher's internal success counter stays at 7
