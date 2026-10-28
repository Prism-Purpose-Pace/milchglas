@id:9522
Feature: Switch a calendar on or off through its enabled flag
  The operator decides which of the owner's calendars count as busy time,
  and a changed flag takes effect without a restart.

  Background:
    Given today is 28 October 2026 in Europe/Berlin
    And calendar 'family' holds an event on 5 November 2026 from 15:00 to 16:00

  Scenario: A disabled calendar adds no busy block
    Given the configuration lists 'work' enabled, 'family' disabled and 'sport' enabled
    When a refresh run completes
    Then the feed lists no busy block on 5 November 2026 from 15:00 to 16:00

  Scenario: A calendar enabled at 10:05 shows in the feed by 10:30 at the latest
    Given the operator set 'family' to enabled at 10:05 on 28 October 2026
    And refresh runs start every 15 minutes from 10:00
    When the booking page fetches the feed at 10:30 on 28 October 2026
    Then the feed lists one busy block on 5 November 2026 from 15:00 to 16:00
