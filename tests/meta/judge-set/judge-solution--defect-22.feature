@id:9122
Feature: Stable identity of a lunch busy block
  The booking page sees the same busy block again after each refresh run instead of a new one.

  Background:
    Given the owner's time zone is Europe/Berlin
    And calendar 'work' holds an event on 24 November 2026 from 13:00 to 14:00

  Scenario: Two refresh runs give the busy block the same UID via Python's hashlib
    Given a refresh run at 06:00 on 2 November 2026 wrote the feed
    When the next refresh run at 06:15 on 2 November 2026 completes
    Then the busy block on 24 November 2026 has the same UID in both feeds

  Scenario: A moved event gets a busy block with a new UID
    Given a refresh run at 06:00 on 2 November 2026 wrote the feed
    And the event then moved to 14:00 to 15:00 on 24 November 2026
    When the next refresh run at 06:15 on 2 November 2026 completes
    Then the busy block on 24 November 2026 from 14:00 to 15:00 has a UID the earlier feed does not hold
