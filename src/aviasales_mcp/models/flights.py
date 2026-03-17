"""Pydantic models for Travelpayouts API v3 responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TicketData(BaseModel):
    origin: str = Field(description="Origin IATA code")
    destination: str = Field(description="Destination IATA code")
    origin_airport: str | None = Field(default=None, description="Origin airport IATA")
    destination_airport: str | None = Field(default=None, description="Destination airport IATA")
    price: int = Field(description="Ticket price in the requested currency")
    airline: str = Field(default="", description="Airline IATA code")
    flight_number: str | None = Field(default=None, description="Flight number")
    departure_at: str = Field(default="", description="Departure datetime ISO-8601")
    return_at: str = Field(default="", description="Return datetime ISO-8601")
    transfers: int = Field(default=0, description="Number of transfers")
    return_transfers: int = Field(default=0, description="Return leg transfers")
    duration: int | None = Field(default=None, description="Total flight duration in minutes")
    duration_to: int | None = Field(default=None, description="Outbound duration in minutes")
    duration_back: int | None = Field(default=None, description="Return duration in minutes")
    link: str = Field(default="", description="Deep link path fragment")
    expires_at: str = Field(default="", description="Price expiration datetime")


class PopularDirection(BaseModel):
    origin: str
    destination: str
    origin_name: str = ""
    destination_name: str = ""
    price: int | None = None
    transfers: int = 0
    airline: str = ""
    departure_at: str = ""
    return_at: str = ""
    link: str = ""
