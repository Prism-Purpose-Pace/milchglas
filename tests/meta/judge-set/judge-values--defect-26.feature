@id:9326
Feature: Invitations the owner has not declined block the owner
  A visitor cannot book the owner into an invitation the owner may attend,
  because every answer except a decline counts as busy.

  Scenario Outline: An invitation the owner did not decline shows as busy
    Given <host> invited the owner to an event on 26 November 2026 from 09:00 to 10:00 UTC
    And the owner's answer is <answer>
    When the refresh run finishes
    Then the feed lists one busy block from 09:00 to 10:00 UTC on 26 November 2026

    Examples:
      | host               | answer        |
      | calendar user 2077 | accepted      |
      | calendar user 1042 | tentative     |
      | Tamsin             | not given yet |
