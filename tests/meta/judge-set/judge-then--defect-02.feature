@id:9202
Feature: Back-to-back events on one morning
  The owner's booking page shows events that overlap or follow each other as one busy block.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: Overlapping events become one busy block
    Given calendar 'work' holds events on 5 November 2026 from 09:00 to 10:30 and from 10:00 to 11:00
    When a refresh run completes
    Then the feed lists one busy block on 5 November 2026 from 09:00 to 11:00

  Scenario: Events that touch at 10:30 become one busy block
    Given calendar 'work' holds events on 5 November 2026 from 09:00 to 10:30 and from 10:30 to 12:00
    When a refresh run completes
    Then Milchglas treats the two events as one
