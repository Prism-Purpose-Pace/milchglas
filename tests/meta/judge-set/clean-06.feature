@id:9506
Feature: Publish each busy block with only the seven allowed lines
  A subscriber of the feed learns when the owner is busy and nothing else
  about the event behind a busy block.

  Background:
    Given today is 28 October 2026 in Europe/Berlin
    And calendar 'work' holds an event on 2 November 2026 from 09:00 to 10:00 titled "Tax adviser" at "Room 4"

  Scenario: A busy block carries the allowed lines and no others
    When a refresh run completes
    Then the busy block in the feed holds only the lines UID, DTSTAMP, DTSTART, DTEND, SUMMARY, TRANSP and STATUS
    And its TRANSP line reads "TRANSP:OPAQUE"

  Scenario: The title and the place of the event stay out of the feed
    When a refresh run completes
    Then no line of the feed holds "Tax adviser" or "Room 4"
