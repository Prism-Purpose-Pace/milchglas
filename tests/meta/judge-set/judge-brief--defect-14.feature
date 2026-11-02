@id:9414
Feature: The owner's answer to an invitation decides the busy block
  A visitor can book a time the owner declined,
  and cannot book a time the owner accepted.

  Scenario Outline: An invitation shows as busy unless the owner declined it
    Given the owner's calendar 'work' holds an invitation on 9 November 2026 from <start> to <end> UTC
    And the owner's answer to that invitation is <answer>
    When the refresh run finishes
    Then the feed lists <result> from <start> to <end> UTC on 9 November 2026

    Examples:
      | answer   | start | end   | result         |
      | accepted | 09:00 | 10:00 | one busy block |
      | declined | 11:00 | 12:00 | no busy block  |
      | accepted | 13:00 | 14:00 | one busy block |
