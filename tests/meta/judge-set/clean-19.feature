@id:9519
Feature: Show a private event as a busy block without its content
  The owner marks an event private and is still protected from bookings over
  it, while nothing of the event reaches a subscriber.

  Background:
    Given today is 28 October 2026 in Europe/Berlin
    And calendar 'work' holds an event marked private on 4 November 2026 from 11:00 to 12:00 titled "Dentist"

  Scenario: The private event blocks its hour
    When a refresh run completes
    Then the feed lists one busy block on 4 November 2026 from 11:00 to 12:00

  Scenario: The title of the private event appears neither in the feed nor in the log
    When a refresh run completes
    Then no line of the feed or of the log holds "Dentist"
