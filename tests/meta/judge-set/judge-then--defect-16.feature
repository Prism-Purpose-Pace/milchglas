@id:9216
Feature: Same calendars, same feed bytes
  The booking page downloads the same feed again when no event changed, so it shows no false update.

  Background:
    Given the owner's time zone is Europe/Berlin
    And calendar 'work' holds an event on 13 November 2026 from 10:00 to 11:00

  Scenario: A refresh run at 09:15 after one at 09:00 with no change
    Given a refresh run at 09:00 on 3 November 2026 wrote the feed
    When the next refresh run at 09:15 on 3 November 2026 completes
    Then the feed is fine
