@id:9220
Feature: One cancelled Tuesday of a weekly event
  The owner's booking page offers the evening when one instance of a weekly event is cancelled.

  Background:
    Given the owner's time zone is Europe/Berlin
    And calendar 'sport' holds an event every Tuesday from 18:00 to 19:00, first on 3 November 2026
    And the instance on 10 November 2026 is cancelled

  Scenario: The cancelled instance on 10 November 2026
    When a refresh run completes
    Then Milchglas forgets the cancelled instance

  Scenario: The instance on 17 November 2026 after the cancelled one
    When a refresh run completes
    Then the feed lists one busy block on 17 November 2026 from 18:00 to 19:00
