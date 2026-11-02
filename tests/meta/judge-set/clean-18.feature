@id:9518
Feature: Show each real occurrence of a recurring event as a busy block
  The owner's weekly recurring event blocks only the evenings it actually
  takes place.

  Background:
    Given today is 28 October 2026 in Europe/Berlin

  Scenario: A deleted and a moved occurrence change only their own evenings
    Given calendar 'sport' holds a recurring event every Tuesday from 18:00 to 19:30 starting 3 November 2026
    And its occurrence on 10 November 2026 is deleted and the one on 17 November 2026 moved to 18 November 2026
    When a refresh run completes
    Then the feed lists busy blocks from 18:00 to 19:30 on 3, 18 and 24 November 2026
    And it lists no busy block on 10 or 17 November 2026
