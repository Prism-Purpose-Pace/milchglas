@id:9417
Feature: The feed opens only with the owner's feed token
  The owner shares the feed only with the booking page,
  because nobody without the feed token can read it.

  Scenario: A start at 09:07 moves back to 09:00 on the grid
    Given the owner's time zone is Europe/Berlin
    And the grid is 15 minutes
    And the owner's calendar 'work' holds an event on 17 November 2026 from 09:07 to 10:00 UTC
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:00 UTC on 17 November 2026

  Scenario: The right feed token opens the feed
    Given the owner's feed token is 'p5Hn2XcV8rTq'
    When the booking page asks for the feed with the token 'p5Hn2XcV8rTq'
    Then the booking page receives the feed

  Scenario: A wrong feed token gets the answer for an unknown address
    Given the owner's feed token is 'p5Hn2XcV8rTq'
    When a visitor asks for the feed with the token 'w3Jm7BzK1dLy'
    Then the visitor gets the same not-found answer as for an unknown address
