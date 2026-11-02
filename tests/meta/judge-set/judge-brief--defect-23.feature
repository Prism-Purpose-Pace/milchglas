@id:9423
Feature: An unchanged calendar gives a byte-identical feed
  The booking page downloads the feed again only when the owner's busy times change,
  because an unchanged calendar leaves the feed exactly as it was.

  Scenario: Two refresh runs over the same events give the same feed
    Given the owner's calendar 'work' holds an event on 23 November 2026 from 09:00 to 10:00 UTC
    And the refresh run at 10:00 UTC on 28 October 2026 wrote the feed
    When the refresh run at 10:15 UTC on 28 October 2026 finishes
    Then the feed is byte for byte the same as after the run at 10:00 UTC

  Scenario: A transparent event leaves no busy block
    Given the owner's calendar 'work' holds a transparent event on 23 November 2026 from 13:00 to 14:00 UTC
    When the refresh run finishes
    Then the feed lists no busy block from 13:00 to 14:00 UTC on 23 November 2026
