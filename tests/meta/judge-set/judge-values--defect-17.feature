@id:9317
Feature: No text of an event reaches the feed
  The owner keeps every word written into an event private,
  because the feed carries the busy time and none of the event's text.

  Scenario Outline: The text of an event stays out of the feed
    Given the owner's calendar 'work' holds an event on 17 November 2026 from 09:00 to 10:00 UTC whose <field> is '<text>'
    When the refresh run finishes
    Then no line of the feed holds '<text>'

    Examples:
      | field       | text                |
      | title       | Dentist at nine     |
      | location    | Room 4 north wing   |
      | description | asdf                |
