@id:9504
Feature: Count an invitation as busy until the owner declines it
  The owner's booking page frees the time of an invitation the owner declined
  and blocks the time of one the owner has not answered yet.

  Background:
    Given today is 28 October 2026 in Europe/Berlin
    And calendar user 1042 sent the owner an invitation in calendar 'work' for 3 November 2026 from 14:00 to 15:00

  Scenario: A declined invitation leaves the afternoon free
    Given the owner declined the invitation from calendar user 1042
    When a refresh run completes
    Then the feed lists no busy block on 3 November 2026

  Scenario: An unanswered invitation blocks its hour
    Given the owner has not answered the invitation from calendar user 1042
    When a refresh run completes
    Then the feed lists one busy block on 3 November 2026 from 14:00 to 15:00
