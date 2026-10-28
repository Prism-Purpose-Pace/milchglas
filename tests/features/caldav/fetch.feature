@id:23
Feature: Fetch from the CalDAV server
  A booking page shows the owner as busy only if Milchglas can
  read the owner's calendars. A server that is slow or overloaded
  for a moment gets another try; an answer that a retry cannot
  change ends the fetch at once.

  Rule: Retry only what can recover (FR-1, Q-15)

    @ORCH-FETCH-2
    Scenario Outline: A client error ends the fetch after one request
      Given the server answers <status>
      When the client fetches one calendar
      Then the fetch fails naming status <status>
      And the server received exactly 1 request

      Examples:
        | status |
        | 400    |
        | 401    |
        | 403    |
        | 404    |
        | 429    |

    @ORCH-FETCH-2
    Scenario Outline: A server error is retried
      Given the server answers <status> and then 207
      When the client fetches one calendar
      Then the fetch succeeds after 2 requests
      And the client waited 1 s

      Examples:
        | status |
        | 500    |
        | 502    |
        | 503    |

    @ORCH-FETCH-1
    Scenario Outline: A timeout is retried three times, then fails
      Given the server lets every <stage> time out
      When the client fetches one calendar
      Then the fetch fails as a timeout
      And the client tried 4 times, each with a 10 s timeout
      And the client waited 1 s, 2 s and 4 s

      Examples:
        | stage      |
        | connection |
        | answer     |

    @ORCH-FETCH-11
    Scenario: A refused connection ends the fetch after one attempt
      Given the server refuses every connection
      When the client fetches one calendar
      Then the fetch fails naming the refused connection
      And the client tried 1 time
