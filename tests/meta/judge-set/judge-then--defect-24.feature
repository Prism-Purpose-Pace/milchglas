@id:9224
Feature: Morning event across the March clock change
  The owner's booking page shows a morning event at the right hour once summer time has begun.

  Background:
    Given the owner's time zone is Europe/Berlin

  Scenario: An event on 26 March 2027 from 08:00 to 09:00, before summer time
    Given calendar 'work' holds an event on 26 March 2027 from 08:00 to 09:00
    When a refresh run completes
    Then the feed lists one busy block on 26 March 2027 from 07:00 to 08:00 UTC

  Scenario: An event on 30 March 2027 from 08:00 to 09:00, in summer time
    Given calendar 'work' holds an event on 30 March 2027 from 08:00 to 09:00
    When a refresh run completes
    Then Milchglas switches its internal offset to two hours
