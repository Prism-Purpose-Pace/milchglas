@id:9403
Feature: Cancelled events leave the owner's time free
  A visitor can book a time whose event was cancelled,
  so the owner loses no booking to an event that will not take place.

  Scenario: A cancelled event leaves no busy block
    Given the owner's calendar 'family' holds a cancelled event on 11 November 2026 from 10:00 to 11:00 UTC
    When the refresh run finishes
    Then the feed lists no busy block on 11 November 2026
    And the feed asks subscribers to fetch it again after 900 seconds

  Scenario: A cancelled instance of a weekly event leaves only that week free
    Given the owner's calendar 'family' holds a weekly event on Wednesdays from 17:00 to 18:00 UTC from 4 November 2026 to 18 November 2026
    And its instance on 11 November 2026 is cancelled
    When the refresh run finishes
    Then the feed lists busy blocks from 17:00 to 18:00 UTC on 4 and 18 November 2026 only
