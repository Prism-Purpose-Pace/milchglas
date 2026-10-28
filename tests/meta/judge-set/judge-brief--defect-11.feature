@id:9411
Feature: Health check marks a feed older than one hour as stale
  The operator sees within an hour that the refresh runs have stopped,
  before a visitor books the owner into a time that is no longer free.

  Scenario Outline: The age of the last success decides fresh or stale
    Given the last refresh run succeeded <age> minutes before the operator asks
    When the operator asks the health check
    Then the health check reports the feed as <answer>

    Examples:
      | age | answer |
      | 59  | fresh  |
      | 60  | stale  |
      | 150 | stale  |
      | 240 | stale  |
