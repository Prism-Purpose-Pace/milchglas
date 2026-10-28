@id:9301
Feature: Past events stay out of the busy feed
  A visitor who books the owner sees only busy times that still lie ahead,
  so the booking page shows no busy block that is already over.

  Scenario: An event before today leaves no busy block
    Given today is 28 October 2026 in Europe/Berlin
    And the owner's calendar 'work' holds an event in the past
    When the refresh run finishes
    Then the feed lists no busy block

  Scenario: An event later today stays in the feed
    Given today is 28 October 2026 in Europe/Berlin
    And the owner's calendar 'work' holds an event on 28 October 2026 from 15:00 to 16:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 15:00 to 16:00 UTC on 28 October 2026
