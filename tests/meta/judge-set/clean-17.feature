@id:9517
Feature: Count tentative events as busy time
  The owner is not double booked over an event that is not yet certain.

  Background:
    Given today is 28 October 2026 in Europe/Berlin
    And the configured summary is "Blocker Privat"

  Scenario: A tentative event blocks its hour like a confirmed one
    Given calendar 'work' holds a tentative event on 6 November 2026 from 10:00 to 11:00
    When a refresh run completes
    Then the feed lists one busy block on 6 November 2026 from 10:00 to 11:00
    And the busy block's summary line reads "SUMMARY:Blocker Privat"

  Scenario: An invitation the owner answered as tentative blocks its time
    Given calendar user 2077 sent the owner an invitation for 9 November 2026 from 15:00 to 16:30
    And the owner answered the invitation as tentative
    When a refresh run completes
    Then the feed lists one busy block on 9 November 2026 from 15:00 to 16:30
