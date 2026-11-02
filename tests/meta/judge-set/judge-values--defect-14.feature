@id:9314
Feature: Events that do not block leave the owner free
  A visitor can book any time the owner will not spend in an event,
  so cancelled, transparent and declined events leave that time free.

  Scenario Outline: An event that does not block leaves no busy block
    Given the owner's calendar '<calendar>' holds a <kind> event on 12 November 2026 from 14:00 to 15:00 UTC
    When the refresh run finishes
    Then the feed lists no busy block on 12 November 2026

    Examples:
      | kind        | calendar |
      | cancelled   | work     |
      | transparent | family   |
      | declined    | xyz      |
