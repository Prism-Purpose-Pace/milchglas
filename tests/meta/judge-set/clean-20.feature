@id:9520
Feature: Refuse a grid that does not fit the owner's time zone
  The operator learns at the next refresh run that a configured grid would put
  busy block edges off the local grid lines.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario Outline: A grid that misses a whole day or the summer time switch is refused
    Given the configured grid is <grid> minutes
    When the refresh run at 10:00 on 28 October 2026 ends
    Then the last error names the grid of <grid> minutes as not dividing <span>

    Examples:
      | grid | span                             |
      | 7    | the 1440 minutes of a day        |
      | 45   | the 60 minute summer time switch |

  Scenario: A 30 minute grid is accepted and rounds to half hours
    Given the configured grid is 30 minutes
    And calendar 'work' holds an event on 2 November 2026 from 09:10 to 09:40
    When the refresh run at 10:00 on 28 October 2026 completes
    Then the feed lists one busy block on 2 November 2026 from 09:00 to 10:00
