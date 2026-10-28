@id:9514
Feature: Change the feed only where the owner's events changed
  A subscribed calendar app sees no busy block vanish and return between
  two refresh runs; only a changed event changes the feed.

  Background:
    Given today is 28 October 2026 in Europe/Berlin
    And calendar 'work' holds 3 events from 10:00 to 11:00, on 2, 4 and 6 November 2026
    And the refresh run at 10:00 on 28 October 2026 wrote the feed

  Scenario: The same 3 events give a byte-identical feed
    When the refresh run at 10:15 completes with the 3 events unchanged
    Then the feed is byte-identical to the one written at 10:00

  Scenario: A moved event changes only its own busy block
    Given the owner moved the event on 4 November 2026 to the hour from 14:00 to 15:00 at 10:05
    When the refresh run at 10:15 completes
    Then only the busy block on 4 November 2026 differs from the feed written at 10:00
    And it now runs from 14:00 to 15:00
    But the busy blocks on 2 and 6 November 2026 keep their UID lines
