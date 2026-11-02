@id:9207
Feature: Free and busy events on one morning
  The owner's booking page blocks the events that make the owner busy and leaves the free ones open.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: An opaque event from 08:00 to 09:00 shows as a busy block
    Given calendar 'work' holds an opaque event on 24 November 2026 from 08:00 to 09:00
    When a refresh run completes
    Then the feed lists one busy block on 24 November 2026 from 08:00 to 09:00

  Scenario: A transparent event from 08:00 to 09:00 leaves the morning free
    Given calendar 'work' holds a transparent event on 24 November 2026 from 08:00 to 09:00
    When a refresh run completes
    Then the transparent event causes no trouble
