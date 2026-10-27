"""config.json is read and validated on every refresh (spec section 8, AC-22, D-16).

The loader rejects with an error that names the key and never the value. The refresh-level
half of the ORCH-CFG rows (no request, old feed kept, exit code) closes with the refresh
tests, which run these cases end to end; only rows the loader settles alone are cited here.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from milchglas.config import ConfigError, config_path, load, parse, read_digest
from milchglas.core.model import window

NOW = datetime(2026, 10, 22, 7, 0, tzinfo=UTC)
DIGEST = "ab" * 32
SALT = "5a" * 16  # the shape `init` prints: 32 lower-case hex characters
MARKER = "BBX-SECRET-VALUE"
EXAMPLE = Path(__file__).resolve().parents[2] / "config.example.json"


def _valid(**changes: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "owner_emails": ["owner@example.org"],
        "calendars": [{"href": "/dav/calendars/svc/a/", "name": "A", "enabled": True}],
        "token_sha256": DIGEST,
        "uid_salt": SALT,
    }
    raw.update(changes)
    return raw


def _error(raw: object) -> str:
    with pytest.raises(ConfigError) as caught:
        parse(raw, NOW)
    return str(caught.value)


def test_defaults_fill_every_optional_key() -> None:
    config = parse(_valid(), NOW)
    assert (config.tz, config.grid_minutes, config.ttl_seconds) == (
        ZoneInfo("Europe/Berlin"),
        15,
        900,
    )
    assert (config.summary, config.allday_mode, config.tentative_mode) == (
        "Blocker Privat",
        "busy",
        "busy",
    )
    assert config.owner_emails == ("owner@example.org",)
    assert config.token_sha256 == DIGEST
    assert config.uid_salt == SALT


def test_missing_window_days_gives_a_33_day_window_orch_cfg_5() -> None:
    config = parse(_valid(), NOW)
    win = window(NOW, config.tz, config.window_days)
    assert win.end_day - win.first_day == timedelta(days=33)


@pytest.mark.parametrize(("days", "ok"), [(0, False), (1, True), (90, True), (91, False)])
def test_window_days_bounds_orch_cfg_5(days: int, *, ok: bool) -> None:
    if ok:
        assert parse(_valid(window_days=days), NOW).window_days == days
    else:
        assert "window_days" in _error(_valid(window_days=days))


@pytest.mark.parametrize("key", ["colour", "CALDAV_SECRET", "caldav_secret", "token"])
def test_unknown_key_is_named_never_its_value_orch_cfg_4(key: str) -> None:
    message = _error(_valid(**{key: MARKER}))
    assert key in message
    assert MARKER not in message


def test_example_configuration_loads_and_holds_no_secret_orch_cfg_4() -> None:
    # As committed the example refuses to run: its uid_salt is a placeholder, so nobody
    # publishes UIDs under a salt every reader of the repository knows.
    with pytest.raises(ConfigError, match=r"^uid_salt"):
        load(EXAMPLE, NOW)
    raw = json.loads(EXAMPLE.read_text())
    config = parse({**raw, "uid_salt": SALT}, NOW)
    assert "token" not in raw
    assert not any("secret" in key.lower() or "password" in key.lower() for key in raw)
    # No known preimage: deploying the example unchanged serves the feed to nobody.
    assert config.token_sha256 == "0" * 64


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        pytest.param(_valid(tz="Mars/Olympus"), "tz", id="unknown-tz"),
        pytest.param(_valid(tz="../../etc/passwd"), "tz", id="tz-path"),
        pytest.param(_valid(tz=""), "tz", id="empty-tz"),
        pytest.param(_valid(grid_minutes=0), "grid_minutes", id="grid-0"),
        pytest.param(_valid(grid_minutes=7), "grid_minutes", id="grid-7"),
        pytest.param(_valid(grid_minutes=45), "grid_minutes", id="grid-45-berlin"),
        pytest.param(_valid(calendars=[]), "calendars", id="no-calendars"),
        pytest.param(
            _valid(calendars=[{"href": "/a/", "name": "A", "enabled": False}]),
            "calendars",
            id="none-enabled",
        ),
        pytest.param(
            _valid(
                calendars=[
                    {"href": "/a/", "name": "A", "enabled": True},
                    {"href": "/a/", "name": "B", "enabled": True},
                ]
            ),
            "calendars[1].href",
            id="duplicate-href",
        ),
        pytest.param(
            _valid(calendars=[{"href": "/a/", "name": "A", "enabled": True, "x": 1}]),
            "calendars[0]",
            id="calendar-unknown-key",
        ),
        pytest.param(
            _valid(calendars=[{"href": "/a/", "name": "A", "enabled": "yes"}]),
            "calendars[0].enabled",
            id="enabled-not-bool",
        ),
        pytest.param(_valid(owner_emails="owner@example.org"), "owner_emails", id="owners-str"),
        pytest.param(_valid(owner_emails=[1]), "owner_emails", id="owner-not-str"),
        pytest.param(_valid(window_days=True), "window_days", id="bool-is-no-int"),
        pytest.param(_valid(ttl_seconds=0), "ttl_seconds", id="ttl-0"),
        pytest.param(_valid(allday_mode="ignore"), "allday_mode", id="allday-later"),
        pytest.param(_valid(tentative_mode="separate"), "tentative_mode", id="tentative-later"),
        pytest.param(_valid(summary="Busy\r\nATTENDEE:x"), "summary", id="summary-crlf"),
        pytest.param(_valid(summary="Busy\u2028x"), "summary", id="summary-u2028"),
        pytest.param(_valid(token_sha256="ab" * 31), "token_sha256", id="digest-short"),
        pytest.param(_valid(token_sha256="zz" * 32), "token_sha256", id="digest-not-hex"),
        pytest.param({**_valid(), "uid_salt": ""}, "uid_salt", id="salt-empty"),
        pytest.param(_valid(uid_salt="salt"), "uid_salt", id="salt-short"),
        pytest.param(_valid(uid_salt=SALT.upper()), "uid_salt", id="salt-upper"),
        pytest.param(_valid(uid_salt=SALT + "0"), "uid_salt", id="salt-long"),
        pytest.param(_valid(uid_salt=f"{SALT}\n"), "uid_salt", id="salt-newline"),
        pytest.param(
            {k: v for k, v in _valid().items() if k != "uid_salt"}, "uid_salt", id="no-salt"
        ),
        pytest.param([], "config", id="not-an-object"),
    ],
)
def test_invalid_configuration_names_the_key(raw: object, key: str) -> None:
    assert key in _error(raw)


def test_errors_never_quote_a_value() -> None:
    for raw in (
        _valid(tz=MARKER),
        _valid(summary=f"{MARKER}\n"),
        _valid(token_sha256=MARKER),
        _valid(uid_salt=MARKER),
        _valid(calendars=[{"href": MARKER, "name": MARKER, "enabled": MARKER}]),
    ):
        assert MARKER not in _error(raw)


def test_non_string_key_is_not_a_json_object() -> None:
    assert _error({1: "x"}) == "config: must be a JSON object"


@pytest.mark.parametrize(
    ("zone", "grid", "ok"),
    [
        ("Europe/Berlin", 60, True),
        ("Europe/Berlin", 90, False),
        ("Asia/Kolkata", 45, True),
        ("Australia/Lord_Howe", 60, False),
    ],
)
def test_grid_is_checked_against_the_zone(zone: str, grid: int, *, ok: bool) -> None:
    raw = _valid(tz=zone, grid_minutes=grid)
    if ok:
        assert parse(raw, NOW).grid_minutes == grid
    else:
        assert "grid_minutes" in _error(raw)


def test_digest_is_stored_lower_case() -> None:
    assert parse(_valid(token_sha256=DIGEST.upper()), NOW).token_sha256 == DIGEST


@pytest.mark.parametrize(
    "content",
    [b"", b"{", b"\xff\xfe\x00", b'{"tz": "Europe/Berlin"', MARKER.encode()],
)
def test_unreadable_file_is_a_config_error(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "config.json"
    path.write_bytes(content)
    with pytest.raises(ConfigError) as caught:
        load(path, NOW)
    assert MARKER not in str(caught.value)
    assert caught.value.__cause__ is None


def test_missing_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load(tmp_path / "config.json", NOW)


def test_load_sees_an_edit_that_replaces_the_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(_valid()))
    assert load(path, NOW).calendars[0].enabled
    replacement = tmp_path / "config.json.new"
    first = {"href": "/dav/calendars/svc/a/", "name": "A", "enabled": True}
    replacement.write_text(json.dumps(_valid(calendars=[first, _second()])))
    replacement.replace(path)
    assert len(load(path, NOW).calendars) == 2


def _second() -> dict[str, object]:
    return {"href": "/dav/calendars/svc/b/", "name": "B", "enabled": False}


def test_config_path_defaults_to_the_working_directory() -> None:
    assert config_path({}) == Path("config.json")
    assert config_path({"MILCHGLAS_CONFIG": "/etc/milchglas/config.json"}) == Path(
        "/etc/milchglas/config.json"
    )


def test_empty_config_variable_means_unset() -> None:
    # A platform form saves an empty field as a set-but-empty variable; Path("") is ".".
    assert config_path({"MILCHGLAS_CONFIG": ""}) == Path("config.json")


def test_read_digest_looks_only_at_its_key(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"token_sha256": DIGEST.upper(), "grid_minutes": 7}))
    assert read_digest(path) == bytes.fromhex(DIGEST)


@pytest.mark.parametrize(
    "content",
    [
        b'{"token_sha256": "' + b"ab" * 31 + b'"}',
        b'{"token_sha256": 5}',
        b"{}",
        b"[]",
        b'{"token_sha256": "ab',
    ],
)
def test_read_digest_refuses_a_malformed_entry(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "config.json"
    path.write_bytes(content)
    with pytest.raises(ConfigError) as caught:
        read_digest(path)
    assert "token_sha256" in str(caught.value)
