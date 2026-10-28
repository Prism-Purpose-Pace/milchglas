@id:9124
Feature: Summer time starts in late March
  The owner's booking page shows a morning event at the right hour after the clock jumps forward,
  using exactly one request per calendar to the server.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: An event the day before summer time starts is one hour ahead of UTC
    Given calendar 'work' holds an event on 27 March 2027 from 09:00 to 10:00
    When a refresh run completes
    Then the feed lists one busy block on 27 March 2027 from 08:00 to 09:00 UTC

  Scenario: An event the day after summer time starts is two hours ahead of UTC
    Given calendar 'work' holds an event on 29 March 2027 from 09:00 to 10:00
    When a refresh run completes
    Then the feed lists one busy block on 29 March 2027 from 07:00 to 08:00 UTC
