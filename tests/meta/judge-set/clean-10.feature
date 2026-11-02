@id:9510
Feature: Report a broken feed token digest to the operator
  The operator learns from the monitor and from the log that a pasted feed
  token digest is broken, before a subscriber notices anything.

  Scenario: A digest cut short by one character turns the health check to 503
    Given the configuration holds a feed token digest of 63 hex characters instead of 64
    And the last successful refresh run ended at 10:15 on 28 October 2026
    When the monitor asks the health check at 10:20 on 28 October 2026
    Then the health check answers status 503

  Scenario: The repaired digest turns the health check back to 200
    Given the operator replaced the digest of 63 hex characters with one of 64 at 10:22 on 28 October 2026
    And the last successful refresh run ended at 10:15 on 28 October 2026
    When the monitor asks the health check at 10:25 on 28 October 2026
    Then the health check answers status 200

  Scenario: The log names the broken setting without its value
    Given the configuration holds a feed token digest of 63 hex characters instead of 64
    When the booking page fetches the feed at 10:20 on 28 October 2026
    Then the log holds a line naming the feed token digest setting
    But the line holds none of the 63 characters
