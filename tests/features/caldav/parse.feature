@id:22
Feature: Read the calendar server's answer
  Milchglas publishes the owner's busy times only from an answer it
  has read in full. Each event leaves as a busy block and nothing
  else; an answer it cannot read in full fails the refresh, so a
  broken object never becomes a free slot.

  Background:
    Given the owner's time zone is Europe/Berlin

  Rule: An event is read as the server wrote it (FR-2, Q-20)

    @PARSE-5
    Scenario Outline: A repeated event lasts as long as written
      Given calendar 1 answers with one instance from 2026-10-24 07:00 UTC lasting "<duration>"
      When Milchglas reads the answer
      Then the owner is busy from 2026-10-24 07:00 UTC to 2026-10-25 <end> UTC

      Examples:
        | duration | end   |
        | P1D      | 08:00 |
        | PT24H    | 07:00 |

    @PARSE-13
    Scenario Outline: A line folded inside a character still reads
      Given calendar 1 answers with an event from 2026-11-02 08:00 UTC to 09:00 UTC whose description "BBX-Kälte" is folded inside the "ä" with <line end>
      When Milchglas reads the answer
      Then the owner is busy from 2026-11-02 08:00 UTC to 2026-11-02 09:00 UTC

      Examples:
        | line end |
        | CRLF     |
        | LF       |

    @PARSE-13
    Scenario: A line longer than 75 octets still reads
      Given calendar 1 answers with an event from 2026-11-02 08:00 UTC to 09:00 UTC whose description line is 200 octets long
      When Milchglas reads the answer
      Then the owner is busy from 2026-11-02 08:00 UTC to 2026-11-02 09:00 UTC

  Rule: Only a plain multistatus answer is read (Q-14, Q-16)

    @PARSE-7
    Scenario: A calendar without events in the window
      Given calendar 1 answers with a multistatus that holds no response
      When Milchglas reads the answer
      Then the owner is busy at no time from calendar 1
      And reading reports no error

    @PARSE-8
    Scenario Outline: An answer that is not a multistatus fails without quoting it
      Given calendar 1 answers with status 207 and the body "<body>"
      When Milchglas reads the answer
      Then reading fails naming status 207 and <size> bytes
      And the error holds nothing of the body

      Examples:
        | body                                            | size |
        | BBX-not a calendar                              | 18   |
        | <d:multistatus xmlns:d="DAV:"><d:response>BBX- | 46   |
        | <d:error xmlns:d="DAV:">BBX-</d:error>          | 38   |

    @PARSE-10
    Scenario Outline: An answer that declares markup is refused unread
      Given calendar 1 answers with a multistatus that starts with <declaration>
      When Milchglas reads the answer
      Then reading fails as a refused declaration
      And no local file was read

      Examples:
        | declaration                            |
        | a bare DOCTYPE                         |
        | an entity bomb                         |
        | an external entity naming a local file |

  Rule: An object that does not read cleanly fails the read (Q-14, NFR-P4)

    @PARSE-11
    Scenario: A garbage start among valid events fails the read
      Given calendar 1 answers with 3 events, the second at "/calendars/svc/BBX-team/ev-2.ics" starting "BBY-tomorrow"
      When Milchglas reads the answer
      Then reading fails as a malformed event naming calendar 1 and the hash of "/calendars/svc/BBX-team/ev-2.ics"
      And no error or log line holds "BBY-tomorrow", "BBX-team" or "ev-2"

    @PARSE-11
    Scenario: A cancelled event with a garbage start still fails the read
      Given calendar 1 answers with a cancelled event at "/calendars/svc/BBX-team/ev-9.ics" starting "BBY-never"
      When Milchglas reads the answer
      Then reading fails as a malformed event naming calendar 1 and the hash of "/calendars/svc/BBX-team/ev-9.ics"
      And no error or log line holds "BBY-never"

    @PARSE-14
    Scenario Outline: A duration beyond any date fails the read
      Given calendar 1 answers with an event at "/calendars/svc/BBX-team/ev-4.ics" whose <property> is "-P999999999DT1S"
      When Milchglas reads the answer
      Then reading fails as a malformed event naming calendar 1 and the hash of "/calendars/svc/BBX-team/ev-4.ics"
      And no error or log line holds "999999999"

      Examples:
        | property      |
        | DURATION      |
        | alarm TRIGGER |

  Rule: Only a complete object expanded by the server counts (FR-2, Q-14)

    @backlog @PARSE-2
    Scenario: Calendar data the server could not find fails the read
      Given calendar 1 answers for "/calendars/svc/BBX-team/ev-5.ics" that its calendar data was not found
      When Milchglas reads the answer
      Then reading fails as a malformed event naming calendar 1 and the hash of "/calendars/svc/BBX-team/ev-5.ics"

    @backlog @PARSE-2
    Scenario: A missing entity tag does not stop the read
      Given calendar 1 answers with an event from 2026-11-02 08:00 UTC to 09:00 UTC and says its entity tag was not found
      When Milchglas reads the answer
      Then the owner is busy from 2026-11-02 08:00 UTC to 2026-11-02 09:00 UTC

    @backlog @PARSE-12
    Scenario Outline: An instance the server left unexpanded fails the read
      Given calendar 1 answers with a weekly event at "/calendars/svc/BBX-team/ev-7.ics" that still holds its <rule>
      When Milchglas reads the answer
      Then reading fails as a malformed event naming calendar 1 and the hash of "/calendars/svc/BBX-team/ev-7.ics"

      Examples:
        | rule  |
        | RRULE |
        | RDATE |
