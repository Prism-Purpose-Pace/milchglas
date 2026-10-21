"""Calendar objects from tests/fixtures/objects, looked up by UID."""

from pathlib import Path

from icalendar import Calendar, Component

OBJECTS = Path(__file__).resolve().parents[1] / "fixtures" / "objects"


def components(name: str) -> list[Component]:
    """Every component of the object file `name` except its VTIMEZONEs."""
    calendar = Calendar.from_ical((OBJECTS / name).read_bytes())
    return [c for c in calendar.subcomponents if c.name != "VTIMEZONE"]


def duration_text(name: str, event: Component) -> str | None:
    """The DURATION value of `event` as the file spells it, `None` if it has none.

    icalendar parses PT24H and P1D alike to one day, so `reduce_event` takes the text.
    """
    uid = str(event["UID"])
    for chunk in (OBJECTS / name).read_text().split("BEGIN:VEVENT")[1:]:
        lines = chunk.split("END:VEVENT")[0].splitlines()
        if f"UID:{uid}" in lines:
            return next(
                (x.removeprefix("DURATION:") for x in lines if x.startswith("DURATION:")), None
            )
    return None


def component(name: str, uid: str) -> Component:
    [found] = [c for c in components(name) if str(c.get("UID")) == uid]
    return found
