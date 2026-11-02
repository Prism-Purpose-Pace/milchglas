@id:9127
Feature: Booking page reads the busy feed
  The booking page gets the owner's busy blocks as calendar data, served through gunicorn and
  the wsgiref helpers of the standard library.

  Scenario: The right feed token gets the feed as calendar data
    Given the feed token is 'Zm4pK2wq'
    When the booking page asks for the feed with token 'Zm4pK2wq'
    Then the answer is 200 with the content type text/calendar
