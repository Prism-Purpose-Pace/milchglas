@id:9227
Feature: Booking page subscribes with the right token
  The booking page that holds the right feed token gets the owner's busy blocks as calendar data.

  Scenario: The right feed token gets the feed
    Given the feed token is 'Pv9cRt4e'
    When the booking page asks for the feed with token 'Pv9cRt4e'
    Then the answer is 200 with the feed as calendar data
    But the answer is otherwise in order
