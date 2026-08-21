import pytest

from aviasales_mcp import validation
from aviasales_mcp.validation import InvalidArgumentError


def test_iata_code_is_normalized_to_upper():
    assert validation.iata_code("mow", "origin") == "MOW"
    assert validation.iata_code("  Bkk  ", "origin") == "BKK"


def test_iata_code_rejects_names_and_wrong_lengths():
    for bad in ("Moscow", "MO", "MOWW", "M0W", "МОВ"):
        with pytest.raises(InvalidArgumentError):
            validation.iata_code(bad, "origin")


def test_iata_code_optionality():
    assert validation.iata_code(None, "origin", required=False) is None
    assert validation.iata_code("  ", "origin", required=False) is None
    with pytest.raises(InvalidArgumentError, match="required"):
        validation.iata_code(None, "origin")


def test_date_or_month_keeps_the_format_it_was_given():
    assert validation.date_or_month("2026-08-15", "departure_at") == "2026-08-15"
    assert validation.date_or_month("2026-08", "departure_at") == "2026-08"
    assert validation.date_or_month(None, "departure_at") is None


def test_date_or_month_rejects_other_formats_and_impossible_dates():
    for bad in ("15.08.2026", "2026/08/15", "aug 2026", "20260815"):
        with pytest.raises(InvalidArgumentError, match="YYYY-MM-DD"):
            validation.date_or_month(bad, "departure_at")
    # Right shape, not a real date.
    with pytest.raises(InvalidArgumentError, match="calendar date"):
        validation.date_or_month("2026-13-40", "departure_at")
    with pytest.raises(InvalidArgumentError, match="calendar date"):
        validation.date_or_month("2026-02-30", "departure_at")


def test_full_date_refuses_a_bare_month():
    assert validation.full_date("2026-09-10", "depart_date") == "2026-09-10"
    assert validation.full_date(None, "return_date") is None
    with pytest.raises(InvalidArgumentError, match="not a month"):
        validation.full_date("2026-09", "depart_date")
    with pytest.raises(InvalidArgumentError, match="required"):
        validation.full_date(None, "depart_date", required=True)


def test_currency_code_falls_back_to_the_default():
    assert validation.currency_code(None, "rub") == "rub"
    assert validation.currency_code("", "usd") == "usd"
    assert validation.currency_code("EUR", "rub") == "eur"
    with pytest.raises(InvalidArgumentError):
        validation.currency_code("rubles", "rub")


def test_two_letter_code_guards_the_dataset_path():
    assert validation.two_letter_code(None, "locale", "en") == "en"
    assert validation.two_letter_code("RU", "locale", "en") == "ru"
    assert validation.two_letter_code(None, "market", "") is None
    # locale is interpolated into /data/<locale>/cities.json.
    for bad in ("../../etc", "e", "eng", "e/n", "e n"):
        with pytest.raises(InvalidArgumentError):
            validation.two_letter_code(bad, "locale", "en")


def test_time_of_day_returns_minutes_since_midnight():
    assert validation.time_of_day("00:00", "depart_after") == 0
    assert validation.time_of_day("7:05", "depart_after") == 425
    assert validation.time_of_day("23:59", "depart_after") == 1439
    assert validation.time_of_day(None, "depart_after") is None


def test_time_of_day_rejects_12h_and_out_of_range():
    for bad in ("7:00 PM", "19h", "1930", "24:00", "12:60"):
        with pytest.raises(InvalidArgumentError):
            validation.time_of_day(bad, "depart_after")


def test_one_of_is_case_insensitive():
    assert validation.one_of("PRICE", "sorting", ("price", "route")) == "price"
    with pytest.raises(InvalidArgumentError, match="must be one of"):
        validation.one_of("cheapest", "sorting", ("price", "route"))


# --- every validation failure must name the fix, not just the fault ---------


def _raise(fn, *args, **kwargs) -> InvalidArgumentError:
    with pytest.raises(InvalidArgumentError) as excinfo:
        fn(*args, **kwargs)
    return excinfo.value


def test_every_validator_attaches_a_hint():
    failures = [
        _raise(validation.iata_code, None, "origin"),
        _raise(validation.iata_code, "Moscow", "origin"),
        _raise(validation.date_or_month, "29.07.2026", "departure_at"),
        _raise(validation.date_or_month, "2026-13-40", "departure_at"),
        _raise(validation.full_date, None, "depart_date", required=True),
        _raise(validation.full_date, "2026-10", "depart_date"),
        _raise(validation.currency_code, "roubles", "rub"),
        _raise(validation.two_letter_code, "russian", "locale"),
        _raise(validation.one_of, "premium", "trip_class", ("economy", "business")),
        _raise(validation.time_of_day, "6pm", "depart_after"),
        _raise(validation.time_of_day, "25:70", "depart_after"),
    ]
    for exc in failures:
        assert exc.hint, f"no hint for: {exc}"
        # The hint is guidance, not a second copy of the complaint.
        assert exc.hint != str(exc)


def test_hint_points_at_the_tool_that_resolves_place_names():
    assert "lookup_cities" in _raise(validation.iata_code, "Bangkok", "destination").hint


def test_month_hint_names_the_tool_that_accepts_a_month():
    hint = _raise(validation.full_date, "2026-10", "depart_date").hint
    assert "get_prices_calendar" in hint
    # It also has to suggest a concrete day inside the month it was given.
    assert "2026-10-15" in hint


def test_enum_hint_lists_the_accepted_values():
    hint = _raise(validation.one_of, "premium", "trip_class", ("economy", "business")).hint
    assert '"economy"' in hint and '"business"' in hint


def test_hint_is_optional_so_bare_raises_still_work():
    exc = InvalidArgumentError("something is off")
    assert exc.hint is None
    assert str(exc) == "something is off"


def test_full_date_hint_never_offers_the_month_form_it_rejects():
    # full_date delegates to date_or_month, whose hint presents "YYYY-MM" as a
    # valid option. On an endpoint that rejects a bare month, passing that hint
    # through would walk the model straight into the next rejection.
    for bad in ("29.07.2026", "2026-13-40", "next tuesday"):
        hint = _raise(validation.full_date, bad, "depart_date").hint
        assert "YYYY-MM-DD" in hint
        assert "or \"YYYY-MM\"" not in hint
        assert "get_prices_calendar" in hint
