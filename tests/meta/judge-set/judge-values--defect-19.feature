@id:9319
Feature: Only the right feed token opens the feed
  The owner shares the busy feed only with the booking page,
  because the feed opens only with its secret token.

  Scenario: The right token opens the feed
    Given the owner's feed token is 'xxxxxxxx'
    When the booking page asks for the feed with that token
    Then the booking page receives the feed

  Scenario: A wrong token gets the answer for an unknown address
    Given the owner's feed token is 'm4Rt9QwZ2kLp'
    When a visitor asks for the feed with the token 'q7Vd2LmP8sNe'
    Then the visitor gets the same not-found answer as for an unknown address
