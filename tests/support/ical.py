"""Calendar objects from tests/fixtures/objects, looked up by UID."""

from pathlib import Path

from icalendar import Calendar, Component

OBJECTS = Path(__file__).resolve().parents[1] / "fixtures" / "objects"


def components(name: str) -> list[Component]:
    """Every component of the object file `name` except its VTIMEZONEs."""
    calendar = Calendar.from_ical((OBJECTS / name).read_bytes())
    return [c for c in calendar.subcomponents if c.name != "VTIMEZONE"]


def component(name: str, uid: str) -> Component:
    [found] = [c for c in components(name) if str(c.get("UID")) == uid]
    return found
