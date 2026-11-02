@id:9315
Feature: The feed shows busy time and nothing of the event
  The owner keeps private what an event is about,
  because a visitor sees only that a time is busy.

  Scenario: A busy block carries the configured summary
    Given the configured summary is 'Blocker Privat'
    And the owner's calendar 'work' holds an event on 13 November 2026 from 09:00 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:00 UTC on 13 November 2026 with the summary 'Blocker Privat'

  Scenario: The event's title stays out of the feed
    Given the owner's calendar 'work' holds an event titled 'lorem ipsum' on 13 November 2026 from 11:00 to 12:00 UTC
    When the refresh run finishes
    Then the feed lists the busy block from 11:00 to 12:00 UTC on 13 November 2026 without the event's title
