@id:9113
Feature: Feed token guards the busy feed
  The owner hands the feed link only to the booking page; a visitor who guesses gets nothing.

  Scenario: The right feed token gets the feed
    Given the feed token is 'q8rT2mWv'
    When the booking page asks for the feed with token 'q8rT2mWv'
    Then the answer is 200 with the feed as calendar data

  Scenario: A wrong feed token gets the same answer as an unknown path
    Given the feed token is 'q8rT2mWv'
    And the token check runs one lookup query against the stored token hash
    When a visitor asks for the feed with token 'q8rT2mWx'
    Then the answer is 404 with the same body as for an unknown path
