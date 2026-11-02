@id:9201
Feature: Short event rounded to the quarter hour
  The owner's booking page covers an event that starts off the grid with a whole busy block.

  Scenario: An event from 11:10 to 11:35 is rounded to the grid
    Given the owner's time zone is Europe/Berlin
    And the grid is 15 minutes
    And calendar 'work' holds an event on 3 November 2026 from 11:10 to 11:35
    When a refresh run completes
    Then the event is rounded correctly
