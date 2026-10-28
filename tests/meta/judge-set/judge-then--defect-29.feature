@id:9229
Feature: Window begins at midnight of the refresh day
  The owner's booking page still shows the busy time from earlier on the day of the refresh run.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: An event from 07:00 to 08:00 on the day of a refresh run at 15:00
    Given the refresh run starts at 15:00 on 9 November 2026
    And calendar 'work' holds an event on 9 November 2026 from 07:00 to 08:00
    When a refresh run completes
    Then the feed lists one busy block on 9 November 2026 from 07:00 to 08:00
    And the morning is covered as it should be
