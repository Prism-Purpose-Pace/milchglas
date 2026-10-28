@id:9512
Feature: Rotate the feed token without a restart
  The operator retires a leaked feed token within one refresh interval, and
  a subscriber holding the new feed token keeps the feed.

  Background:
    Given the operator pasted the digest of a new feed token into the configuration at 10:00 on 28 October 2026
    And a refresh run completed at 10:15 on 28 October 2026

  Scenario: The old feed token gets the 404 of an unknown path
    When someone fetches the feed with the old feed token at 10:20
    Then the answer is status 404
    And its body is byte-identical to the answer for an unknown path

  Scenario: The new feed token gets the feed
    When someone fetches the feed with the new feed token at 10:20
    Then the answer is status 200 with the type "text/calendar"
