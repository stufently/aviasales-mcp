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

_IATA_HINT = (
    "Send a 3-letter IATA code. Resolve a place name with lookup_cities "
    '(city codes like "MOW", "BKK"), or find_nearest_airports when the town has '
    "no airport of its own. Do not guess the code."
)

_DATE_HINT = (
    'Send the date as "YYYY-MM-DD" for a single day or "YYYY-MM" for a whole '
    'month. Resolve relative dates ("next March", "in two weeks") to a calendar '
    "date yourself before calling."
)

_FULL_DATE_HINT = (
    'Send the date as a full "YYYY-MM-DD". This endpoint rejects a bare month; '
    "for a whole month use get_prices_calendar instead."
)

_CURRENCY_HINT = (
    'Send a 3-letter ISO 4217 currency code ("rub", "usd", "eur", "thb"), or '
    "omit currency to use the server's configured default."
)

_TIME_HINT = (
    'Send a 24-hour time as "HH:MM" ("06:00", "18:30"). For a window that wraps '
    "midnight set depart_after later than depart_before."
)


class InvalidArgumentError(ValueError):
    """Raised when a tool argument cannot be sent to the API as-is.

    The message says what is wrong; ``hint`` says what to send instead. They are
    separate because the response contract puts them in separate fields — a
    model that reads only ``hint`` on failure would otherwise get nothing back
    from a validation error, which is the one failure it can always fix itself.
    """

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


def iata_code(value: str | None, field: str, *, required: bool = True) -> str | None:
    """Normalize a 3-letter IATA city/airport code to upper case.

    Travelpayouts answers a bad code with an empty result set rather than an
    error, so the check has to happen here.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise InvalidArgumentError(
                f'{field} is required and must be a 3-letter IATA code (e.g. "MOW", "BKK"). '
                f"Use lookup_cities or lookup_airports to turn a place name into a code.",
                f"Set {field} to a 3-letter IATA code and call again. {_IATA_HINT}",
            )
        return None
    text = str(value).strip()
    if not _IATA_RE.match(text):
        raise InvalidArgumentError(
            f'{field} must be a 3-letter IATA code (e.g. "MOW", "BKK"), got "{value}". '
            f"Use lookup_cities or lookup_airports to turn a place name into a code.",
            f'Look up "{value}" with lookup_cities and retry with the code it returns. '
            f"{_IATA_HINT}",
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
            f'got "{value}".',
            f"Reformat {field} and call again. {_DATE_HINT}",
        )
    try:
        datetime.strptime(text, fmt)
    except ValueError:
        # Matches the shape but is not a real date, e.g. 2026-13-40.
        raise InvalidArgumentError(
            f'{field} is not a valid calendar date: "{value}".',
            f"The format is right but that day does not exist — check the month is 01-12 "
            f"and the day is inside that month, then call again. {_DATE_HINT}",
        ) from None
    return text


def full_date(value: str | None, field: str, *, required: bool = False) -> str | None:
    """Validate a ``YYYY-MM-DD`` date, refusing a bare month.

    Some endpoints (the week matrix) reject ``2026-10`` with a 400, so the month
    form that ``date_or_month`` allows has to be caught before the call.
    """
    try:
        parsed = date_or_month(value, field)
    except InvalidArgumentError as exc:
        # date_or_month's hint offers "YYYY-MM" as a valid option. Here it is
        # not one, so passing that hint through would walk the model straight
        # into the next rejection. Replace it rather than append to it.
        raise InvalidArgumentError(
            str(exc), f"Reformat {field} and call again. {_FULL_DATE_HINT}"
        ) from None
    if parsed is None:
        if required:
            raise InvalidArgumentError(
                f'{field} is required and must be a full date "YYYY-MM-DD" (e.g. "2026-09-10").',
                f"Set {field} to a specific day and call again. {_FULL_DATE_HINT}",
            )
        return None
    if len(parsed) != 10:
        raise InvalidArgumentError(
            f'{field} must be a full date "YYYY-MM-DD" (e.g. "2026-09-10"), not a month. '
            "For a whole month use get_prices_calendar.",
            f"Pick a day inside {parsed} (e.g. \"{parsed}-15\") and call again, or switch to "
            f"get_prices_calendar to cover the whole month. {_FULL_DATE_HINT}",
        )
    return parsed


def currency_code(value: str | None, default: str) -> str:
    """Validate a 3-letter currency code, falling back to the configured default."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return default.strip().lower()
    text = str(value).strip()
    if not _IATA_RE.match(text):
        raise InvalidArgumentError(
            f'currency must be a 3-letter code (e.g. "rub", "usd", "eur"), got "{value}".',
            _CURRENCY_HINT,
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
            f'{field} must be a 2-letter code (e.g. "en", "ru", "us"), got "{value}".',
            f'Send {field} as a 2-letter code ("en", "ru", "us", "th"), or omit it to use '
            f"the server's configured default.",
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
        raise InvalidArgumentError(
            f'{field} must be one of {options}, got "{value}".',
            f"Set {field} to one of {options} and call again, or omit it for the default "
            f'("{allowed[0]}"). No other value is accepted.',
        )
    return text


def time_of_day(value: str | None, field: str) -> int | None:
    """Parse a 24-hour ``HH:MM`` time into minutes since midnight."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    text = str(value).strip()
    m = _TIME_RE.match(text)
    if not m:
        raise InvalidArgumentError(
            f'{field} must be a 24-hour time "HH:MM" (e.g. "18:30"), got "{value}".',
            f"Convert {field} to 24-hour clock time and call again. {_TIME_HINT}",
        )
    hours, minutes = int(m.group(1)), int(m.group(2))
    if hours > 23 or minutes > 59:
        raise InvalidArgumentError(
            f'{field} is not a valid time of day: "{value}".',
            f"Hours must be 00-23 and minutes 00-59. {_TIME_HINT}",
        )
    return hours * 60 + minutes
