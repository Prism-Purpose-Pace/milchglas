@id:9102
Feature: Merging two events that touch
  The owner's booking page shows back-to-back events as one busy block, not two.

  Background:
    Given the owner's time zone is Europe/Berlin
    And the refresher keeps every fetched event in a cache for 10 minutes

  Scenario: Events from 10:00 to 10:30 and from 10:30 to 11:00 become one busy block
    Given calendar 'work' holds events on 4 November 2026 from 10:00 to 10:30 and from 10:30 to 11:00
    When a refresh run completes
    Then the feed lists one busy block on 4 November 2026 from 10:00 to 11:00

  Scenario: Events an hour apart stay two busy blocks
    Given calendar 'work' holds events on 4 November 2026 from 10:00 to 10:30 and from 11:30 to 12:00
    When a refresh run completes
    Then the feed lists two busy blocks on 4 November 2026, from 10:00 to 10:30 and from 11:30 to 12:00
