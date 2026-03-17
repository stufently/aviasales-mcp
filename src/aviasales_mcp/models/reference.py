"""Reference data models (airlines, airports, cities, countries)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Airline(BaseModel):
    name: str = ""
    name_translations: dict[str, str] = Field(default_factory=dict)
    iata: str = ""
    icao: str | None = None
    is_lowcost: bool = False


class Airport(BaseModel):
    name: str = ""
    name_translations: dict[str, str] = Field(default_factory=dict)
    iata: str = ""
    city_code: str = ""
    country_code: str = ""
    coordinates: dict[str, float] = Field(default_factory=dict)
    time_zone: str = ""


class City(BaseModel):
    name: str = ""
    name_translations: dict[str, str] = Field(default_factory=dict)
    code: str = ""
    country_code: str = ""
    coordinates: dict[str, float] = Field(default_factory=dict)
    time_zone: str = ""


class Country(BaseModel):
    name: str = ""
    name_translations: dict[str, str] = Field(default_factory=dict)
    code: str = ""
    currency: str = ""
