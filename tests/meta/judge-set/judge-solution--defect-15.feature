@id:9115
Feature: Last error names the calendar at fault
  The operator learns from the last error which calendar to look at, without seeing any event.

  Scenario: A calendar that refuses connections is named in the last error
    Given the server for calendar 'sport' refuses every connection
    When a refresh run ends
    Then the last error names calendar 'sport' as unreachable

  Scenario: A calendar answer the lxml parser rejects is named in the last error
    Given calendar 'sport' answers 207 with the body 'not a calendar'
    When a refresh run ends
    Then the last error names calendar 'sport' as unreadable
