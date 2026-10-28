@id:9211
Feature: Guessed feed token learns nothing
  The owner's busy feed stays hidden from a visitor who tries a token that is not the right one.

  Scenario: A token that differs in its last character is turned away
    Given the feed token is 'Hx3vNq7L'
    When a visitor asks for the feed with token 'Hx3vNq7M'
    Then the wrong feed token is dealt with appropriately
