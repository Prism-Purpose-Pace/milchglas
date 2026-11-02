@id:9321
Feature: A family calendar shared read-only blocks bookings
  A visitor cannot book the owner during family events,
  because a calendar shared with the owner counts as busy time.

  Scenario: An event in a shared family calendar shows as busy
    Given Edda Quernstein shares her calendar 'family' with the owner read-only
    And the calendar 'family' holds an event on 21 November 2026 from 10:00 to 12:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 10:00 to 12:00 UTC on 21 November 2026

  Scenario: A shared calendar without events leaves no busy block
    Given calendar user 1042 shares the calendar 'sport' with the owner read-only
    And the calendar 'sport' holds no event in November 2026
    When the refresh run finishes
    Then the feed lists no busy block in November 2026
