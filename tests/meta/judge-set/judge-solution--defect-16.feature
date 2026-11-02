@id:9116
Feature: Unchanged calendars give a byte-identical feed
  The booking page downloads nothing new when nothing changed, because Milchglas
  calls emit_feed() only once per refresh run.

  Background:
    Given the owner's time zone is Europe/Berlin
    And calendar 'work' holds an event on 3 November 2026 from 09:00 to 10:00

  Scenario: A second refresh run with no change writes the same bytes
    Given a refresh run at 06:00 on 2 November 2026 wrote the feed
    When the next refresh run at 06:15 on 2 November 2026 completes
    Then the feed is byte for byte the same as after the run at 06:00
