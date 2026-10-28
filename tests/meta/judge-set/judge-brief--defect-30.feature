@id:9430
Feature: A rotated feed token replaces the old one
  The owner can lock out everyone who knew the old feed token,
  while the booking page reads the feed with the new feed token.

  Scenario: The new feed token opens the feed
    Given the owner's feed token was 'g6Tn4WqB9cHs'
    And the owner rotated the feed token to 'v1Rk8ZpD3mJx'
    When the booking page asks for the feed with the feed token 'v1Rk8ZpD3mJx'
    Then the booking page receives the feed

  Scenario: The old feed token gets the answer for an unknown address
    Given the owner's feed token was 'g6Tn4WqB9cHs'
    And the owner replaced that access key with 'v1Rk8ZpD3mJx'
    When a visitor asks for the feed with the feed token 'g6Tn4WqB9cHs'
    Then the visitor gets the same not-found answer as for an unknown address
