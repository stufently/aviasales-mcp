"""Argument validation for tool inputs — fail before spending an API call.

The flight tools used to forward whatever they were given straight to
Travelpayouts. A typo'd IATA code or a ``29.07.2026`` date then cost a request
and came back as an empty ``data`` list, which a model reads as "there are no
flights on this route" rather than "you asked wrong". Rejecting it up front,
with the expected format spelled out, turns a dead end into something the model
can fix on its own.
"""

from __future__ import annotations

import re
from datetime import datetime

_IATA_RE = re.compile(r"^[A-Za-z]{3}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


class InvalidArgumentError(ValueError):
    """Raised when a tool argument cannot be sent to the API as-is."""


def iata_code(value: str | None, field: str, *, required: bool = True) -> str | None:
    """Normalize a 3-letter IATA city/airport code to upper case.

    Travelpayouts answers a bad code with an empty result set rather than an
    error, so the check has to happen here.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise InvalidArgumentError(
                f'{field} is required and must be a 3-letter IATA code (e.g. "MOW", "BKK"). '
                f"Use lookup_cities or lookup_airports to turn a place name into a code."
            )
        return None
    text = str(value).strip()
    if not _IATA_RE.match(text):
        raise InvalidArgumentError(
            f'{field} must be a 3-letter IATA code (e.g. "MOW", "BKK"), got "{value}". '
            f"Use lookup_cities or lookup_airports to turn a place name into a code."
        )
    return text.upper()


def date_or_month(value: str | None, field: str) -> str | None:
    """Validate a ``YYYY-MM-DD`` date or a ``YYYY-MM`` month, keeping the format."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    text = str(value).strip()
    if _DATE_RE.match(text):
        fmt = "%Y-%m-%d"
    elif _MONTH_RE.match(text):
        fmt = "%Y-%m"
    else:
        raise InvalidArgumentError(
            f'{field} must be "YYYY-MM-DD" or "YYYY-MM" (e.g. "2026-08-15" or "2026-08"), '
            f'got "{value}".'
        )
    try:
        datetime.strptime(text, fmt)
    except ValueError:
        # Matches the shape but is not a real date, e.g. 2026-13-40.
        raise InvalidArgumentError(f'{field} is not a valid calendar date: "{value}".') from None
    return text


def full_date(value: str | None, field: str, *, required: bool = False) -> str | None:
    """Validate a ``YYYY-MM-DD`` date, refusing a bare month.

    Some endpoints (the week matrix) reject ``2026-10`` with a 400, so the month
    form that ``date_or_month`` allows has to be caught before the call.
    """
    parsed = date_or_month(value, field)
    if parsed is None:
        if required:
            raise InvalidArgumentError(
                f'{field} is required and must be a full date "YYYY-MM-DD" (e.g. "2026-09-10").'
            )
        return None
    if len(parsed) != 10:
        raise InvalidArgumentError(
            f'{field} must be a full date "YYYY-MM-DD" (e.g. "2026-09-10"), not a month. '
            "For a whole month use get_prices_calendar."
        )
    return parsed


def currency_code(value: str | None, default: str) -> str:
    """Validate a 3-letter currency code, falling back to the configured default."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return default.strip().lower()
    text = str(value).strip()
    if not _IATA_RE.match(text):
        raise InvalidArgumentError(
            f'currency must be a 3-letter code (e.g. "rub", "usd", "eur"), got "{value}".'
        )
    return text.lower()


def two_letter_code(value: str | None, field: str, default: str = "") -> str | None:
    """Validate a 2-letter locale/market code, falling back to a configured default.

    ``locale`` is interpolated into a dataset path (``/data/<locale>/cities.json``),
    so this is also what keeps a caller from walking out of it.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        value = default
    text = str(value).strip().lower()
    if not text:
        return None
    if not re.fullmatch(r"[a-z]{2}", text):
        raise InvalidArgumentError(
            f'{field} must be a 2-letter code (e.g. "en", "ru", "us"), got "{value}".'
        )
    return text


def one_of(value: str, field: str, allowed: tuple[str, ...]) -> str:
    """Validate an enum-style argument.

    The allowed values also reach the model through ``Literal`` annotations in
    the tool schema; this is the runtime half of the same contract.
    """
    text = str(value).strip().lower()
    if text not in allowed:
        options = ", ".join(f'"{a}"' for a in allowed)
        raise InvalidArgumentError(f'{field} must be one of {options}, got "{value}".')
    return text


def time_of_day(value: str | None, field: str) -> int | None:
    """Parse a 24-hour ``HH:MM`` time into minutes since midnight."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    text = str(value).strip()
    m = _TIME_RE.match(text)
    if not m:
        raise InvalidArgumentError(
            f'{field} must be a 24-hour time "HH:MM" (e.g. "18:30"), got "{value}".'
        )
    hours, minutes = int(m.group(1)), int(m.group(2))
    if hours > 23 or minutes > 59:
        raise InvalidArgumentError(f'{field} is not a valid time of day: "{value}".')
    return hours * 60 + minutes
