@id:9213
Feature: Last error after a refused connection
  The operator finds out from the last error why the feed stopped changing.

  Scenario: Calendar 'family' refuses every connection
    Given the server for calendar 'family' refuses every connection
    When a refresh run ends
    Then the error is handled gracefully
