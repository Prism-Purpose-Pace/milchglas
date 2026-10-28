@id:23
Feature: Fetch from the CalDAV server
  A booking page shows the owner as busy only if Milchglas can
  read the owner's calendars. A server that is slow or overloaded
  for a moment gets another try; an answer that a retry cannot
  change ends the fetch at once.

  @id:77 @ORCH-FETCH-5
  Scenario Outline: A redirect ends the fetch without following it
    Never follow the server to another address (NFR-S7).

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
      Then the fetch succeeds after one retry
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
      Then the fetch succeeds after one check and one query
      And no request reached the server without the credentials

    @ORCH-FETCH-9
    Scenario: A cookie the server sets is not sent back
      Given the server answers 503 with a session cookie and then 207
      When the client fetches one calendar
      Then the fetch succeeds after one retry
      And no request reached the server with a cookie

  @id:77
  Rule: Stop reading an answer that grows past 16 MiB (Q-15)

    @ORCH-FETCH-4
    Scenario: An answer over 16 MiB is cut off mid-stream
      Given the server answers 207 with 64 MiB of calendar data and no length
      When the client fetches one calendar
      Then the fetch fails naming the 16 MiB limit
      And the server could not send the whole answer
      And the server received exactly 1 query

    @ORCH-FETCH-4
    Scenario: An answer of exactly 16 MiB is read whole
      Given the server answers 207 with 16 MiB of calendar data and no length
      When the client fetches one calendar
      Then the fetch succeeds with all 16 MiB

  @id:77
  Rule: Ask every enabled calendar, in configuration order, for the window (FR-1)

    @ORCH-FETCH-7
    Scenario: The query covers the window in UTC
      The window spans the end of summer time on 2026-10-25: its two ends have different offsets.

      Given the window runs from 2026-10-20 to 2026-11-22 in Europe/Berlin
      When the client fetches one calendar
      Then the server received a calendar query at depth 1
      And it asked for the events from 20261019T220000Z to 20261121T230000Z, expanded over the same range

    @ORCH-FETCH-7
    Scenario: Only enabled calendars are asked, in configuration order
      Given the configuration lists Privat enabled, Familie disabled and Arbeit enabled
      When the client fetches the calendars
      Then the server received queries for Privat and then Arbeit
      And the server received no request for Familie

  @id:77
  Rule: Read only a calendar that someone else owns and the service user cannot change (FR-1, NFR-S3)

    @ORCH-FETCH-8
    Scenario Outline: A calendar the service user must not read from ends the fetch
      Given the configuration lists Privat enabled, Familie disabled and Arbeit enabled
      And the server describes Arbeit as a <resource> owned by <owner> with <privileges>
      When the client fetches the calendars
      Then the fetch fails naming calendars[2] as <refusal>
      And the server received no query for Arbeit

      Examples:
        | resource   | owner         | privileges  | refusal                      |
        | collection | svc-milchglas | read, write | not a calendar               |
        | calendar   | svc-milchglas | read, write | owned by the service user    |
        | calendar   | the owner     | read, write | writable by the service user |

    @ORCH-FETCH-8
    Scenario: A calendar the owner shares read-only is fetched
      Nextcloud grants a read-only share write-properties, so the share can be renamed.

      Given the server describes Privat as a calendar owned by the owner with read, write-properties
      When the client fetches one calendar
      Then the fetch succeeds after one check and one query
