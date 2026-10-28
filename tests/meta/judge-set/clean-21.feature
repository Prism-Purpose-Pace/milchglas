@id:9521
Feature: Accept a window from 1 to 90 days
  The operator sets how many days ahead the feed lists busy blocks, and a
  value outside that range stops the refresh run before the feed changes.

  Background:
    Given today is 28 October 2026 in Europe/Berlin
    And calendar 'work' holds an event from 09:00 to 10:00 on every day from 1 October 2026 to 31 March 2027

  Rule: The window lies between 1 and 90 days

    Scenario Outline: A window just outside the range is refused
      Given the configured window is <days> days
      When a refresh run ends
      Then the last error names the window of <days> days as outside 1 to 90

      Examples:
        | days |
        | 0    |
        | 91   |

    Scenario Outline: A window at either end of the range is accepted
      Given the configured window is <days> days
      When a refresh run completes
      Then the last busy block in the feed is the one on <last_day> from 09:00 to 10:00

      Examples:
        | days | last_day        |
        | 1    | 28 October 2026 |
        | 90   | 25 January 2027 |
