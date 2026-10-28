@id:9318
Feature: A calendar shared with the owner counts as busy
  A visitor sees the owner busy during the events of a calendar someone shares,
  so a shared calendar blocks bookings like the owner's own.

  Scenario: An event in a calendar shared by calendar user 1042 shows as busy
    Given calendar user 1042 shares the calendar 'family' with the owner read-only
    And the calendar 'family' holds an event on 18 November 2026 from 16:00 to 17:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 16:00 to 17:00 UTC on 18 November 2026

  Scenario: An event in a calendar shared by a second person shows as busy
    Given calendar user 1042 shares the calendar 'family' with the owner read-only
    And calendar user 2077 shares the calendar 'dummy' with the owner read-only
    And that calendar holds an event on 19 November 2026 from 07:00 to 08:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 07:00 to 08:00 UTC on 19 November 2026
