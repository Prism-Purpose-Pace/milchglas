@id:9525
Feature: Fold long feed lines at 75 octets
  A strict calendar app reads the feed even when the operator configures a
  long summary for the busy blocks.

  Background:
    Given today is 28 October 2026 in Europe/Berlin
    And the configured summary is "Busy with family matters for the whole afternoon and evening of this day only"
    And calendar 'family' holds an event on 6 November 2026 from 13:00 to 18:00

  Scenario: A summary longer than one line is folded
    When a refresh run completes
    Then no line of the feed is longer than 75 octets
    And the unfolded SUMMARY line reads the configured summary in full
