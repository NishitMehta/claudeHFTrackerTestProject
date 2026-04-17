"""
Thin wrapper around the official Amadeus Python SDK.

Uses the test environment by default. Set AMADEUS_HOSTNAME=production
in env vars (and use production keys) once you outgrow the test quota.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from amadeus import Client, ResponseError

log = logging.getLogger(__name__)


@dataclass
class FlightOffer:
    price: float
    currency: str
    airline: str
    departure_time: str
    arrival_time: str
    duration_minutes: int
    stops: int
    booking_link: str | None = None


@dataclass
class HotelOffer:
    hotel_name: str
    hotel_id: str
    total_price: float
    currency: str
    check_in: str
    check_out: str
    room_type: str | None = None


class AmadeusClient:
    """Wraps the Amadeus SDK with the two endpoints we care about."""

    def __init__(self) -> None:
        api_key = os.environ.get("AMADEUS_API_KEY")
        api_secret = os.environ.get("AMADEUS_API_SECRET")
        if not api_key or not api_secret:
            raise RuntimeError(
                "AMADEUS_API_KEY and AMADEUS_API_SECRET must be set "
                "in environment variables (or GitHub Secrets)."
            )
        hostname = os.environ.get("AMADEUS_HOSTNAME", "test")
        self.client = Client(
            client_id=api_key,
            client_secret=api_secret,
            hostname=hostname,
        )

    # ---------- Flights ----------

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        adults: int = 1,
        travel_class: str = "ECONOMY",
        currency: str = "INR",
        max_results: int = 5,
    ) -> list[FlightOffer]:
        params: dict[str, Any] = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date,
            "adults": adults,
            "travelClass": travel_class,
            "currencyCode": currency,
            "max": max_results,
        }
        if return_date:
            params["returnDate"] = return_date

        try:
            resp = self.client.shopping.flight_offers_search.get(**params)
        except ResponseError as e:
            log.error("Amadeus flight search failed: %s", e)
            return []

        offers: list[FlightOffer] = []
        for raw in resp.data or []:
            try:
                offers.append(self._parse_flight(raw))
            except Exception as e:  # noqa: BLE001
                log.warning("skipping malformed flight offer: %s", e)
        return offers

    @staticmethod
    def _parse_flight(raw: dict) -> FlightOffer:
        price = float(raw["price"]["grandTotal"])
        currency = raw["price"]["currency"]
        itin = raw["itineraries"][0]
        segments = itin["segments"]
        first = segments[0]
        last = segments[-1]
        airline = first["carrierCode"]

        # ISO 8601 duration like "PT5H30M"
        duration_iso = itin.get("duration", "PT0M")
        duration_minutes = _iso_duration_to_minutes(duration_iso)

        return FlightOffer(
            price=price,
            currency=currency,
            airline=airline,
            departure_time=first["departure"]["at"],
            arrival_time=last["arrival"]["at"],
            duration_minutes=duration_minutes,
            stops=len(segments) - 1,
        )

    # ---------- Hotels ----------

    def list_hotel_ids(self, city_code: str, max_hotels: int = 10) -> list[str]:
        try:
            resp = self.client.reference_data.locations.hotels.by_city.get(
                cityCode=city_code,
            )
        except ResponseError as e:
            log.error("Hotel-by-city lookup failed for %s: %s", city_code, e)
            return []
        ids = [h["hotelId"] for h in (resp.data or []) if "hotelId" in h]
        return ids[:max_hotels]

    def search_hotel_offers(
        self,
        hotel_ids: list[str],
        check_in: str,
        check_out: str,
        adults: int = 2,
        rooms: int = 1,
        currency: str = "INR",
    ) -> list[HotelOffer]:
        if not hotel_ids:
            return []

        # Amadeus accepts a comma-separated list, but caps at ~50 ids per call.
        chunk = ",".join(hotel_ids[:50])
        try:
            resp = self.client.shopping.hotel_offers_search.get(
                hotelIds=chunk,
                checkInDate=check_in,
                checkOutDate=check_out,
                adults=adults,
                roomQuantity=rooms,
                currency=currency,
                bestRateOnly=True,
            )
        except ResponseError as e:
            log.error("Hotel offers search failed: %s", e)
            return []

        offers: list[HotelOffer] = []
        for raw in resp.data or []:
            try:
                offers.append(self._parse_hotel(raw))
            except Exception as e:  # noqa: BLE001
                log.warning("skipping malformed hotel offer: %s", e)
        return offers

    @staticmethod
    def _parse_hotel(raw: dict) -> HotelOffer:
        hotel = raw["hotel"]
        offer = raw["offers"][0]
        price = float(offer["price"]["total"])
        currency = offer["price"]["currency"]
        room_type = offer.get("room", {}).get("typeEstimated", {}).get("category")
        return HotelOffer(
            hotel_name=hotel.get("name", "Unknown"),
            hotel_id=hotel.get("hotelId", ""),
            total_price=price,
            currency=currency,
            check_in=offer.get("checkInDate", ""),
            check_out=offer.get("checkOutDate", ""),
            room_type=room_type,
        )


def _iso_duration_to_minutes(iso: str) -> int:
    """Parse ISO 8601 duration like 'PT5H30M' -> minutes."""
    if not iso.startswith("PT"):
        return 0
    body = iso[2:]
    hours = 0
    minutes = 0
    num = ""
    for ch in body:
        if ch.isdigit():
            num += ch
        elif ch == "H":
            hours = int(num or 0)
            num = ""
        elif ch == "M":
            minutes = int(num or 0)
            num = ""
        else:
            num = ""
    return hours * 60 + minutes
