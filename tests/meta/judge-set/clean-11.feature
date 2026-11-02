@id:9511
Feature: Answer a wrong feed token exactly like an unknown path
  Nobody who guesses at the feed learns whether it exists; only the holder
  of the feed token receives the owner's busy times.

  Scenario: A token one character off gets the same 404 as an unknown path
    Given a token that differs from the feed token only in its last character
    When someone fetches the feed with that token
    Then the answer is status 404
    And its body is byte-identical to the answer for the unknown path "/calendar.ics"

  Scenario: The feed token gets the feed
    Given the operator handed the feed token to the booking page
    When the booking page fetches the feed with the feed token
    Then the answer is status 200 with the type "text/calendar"
    And it carries the header "X-Robots-Tag: noindex"
