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

  @id:77
  Rule: Send the credentials at once and keep nothing the server hands out (FR-1)

    @ORCH-FETCH-9
    Scenario: The first request already carries the credentials
      Given the server challenges every request without the service user's credentials
      When the client fetches one calendar
      Then the fetch succeeds after 1 request
      And no request reached the server without the credentials

    @ORCH-FETCH-9
    Scenario: A cookie the server sets is not sent back
      Given the server answers 503 with a session cookie and then 207
      When the client fetches one calendar
      Then the fetch succeeds after 2 requests
      And no request reached the server with a cookie

  @id:77
  Rule: Never follow the server to another address (NFR-S7)

    @ORCH-FETCH-5
    Scenario Outline: A redirect ends the fetch without following it
      Given the server answers <status> pointing to a second server
      When the client fetches one calendar
      Then the fetch fails naming status <status> and the second server's host
      And the second server received no request
      And the server received exactly 1 request

      Examples:
        | status |
        | 301    |
        | 302    |
        | 307    |
        | 308    |

  @id:77
  Rule: Stop reading an answer that grows past 16 MiB (Q-15)

    @ORCH-FETCH-4
    Scenario: An answer over 16 MiB is cut off mid-stream
      Given the server answers 207 with 64 MiB of calendar data and no length
      When the client fetches one calendar
      Then the fetch fails naming the 16 MiB limit
      And the server could not send the whole answer
      And the server received exactly 1 request

    @ORCH-FETCH-4
    Scenario: An answer of exactly 16 MiB is read whole
      Given the server answers 207 with 16 MiB of calendar data and no length
      When the client fetches one calendar
      Then the fetch succeeds with all 16 MiB
