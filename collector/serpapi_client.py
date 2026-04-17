"""
SerpAPI wrapper for Google Flights and Google Hotels.

Why SerpAPI: The Amadeus self-service portal is being decommissioned in
mid-2026 and signups are closed. SerpAPI is a stable, well-maintained
service that exposes Google Flights and Google Hotels as JSON APIs,
with a free tier of 250 searches/month — plenty for personal tracking.

Docs: https://serpapi.com/google-flights-api
      https://serpapi.com/google-hotels-api
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)

API_URL = "https://serpapi.com/search.json"
TIMEOUT = 30


@dataclass
class FlightOffer:
    price: float
    currency: str
    airline: str
    departure_time: str
    arrival_time: str
    duration_minutes: int
    stops: int


@dataclass
class HotelOffer:
    hotel_name: str
    total_price: float
    currency: str
    check_in: str
    check_out: str
    rating: float | None = None
    hotel_id: str = ""


_TRAVEL_CLASS_MAP = {
    "ECONOMY": 1,
    "PREMIUM_ECONOMY": 2,
    "BUSINESS": 3,
    "FIRST": 4,
}


class SerpApiClient:
    def __init__(self) -> None:
        api_key = os.environ.get("SERPAPI_KEY")
        if not api_key:
            raise RuntimeError(
                "SERPAPI_KEY must be set in environment variables "
                "(or GitHub Secrets)."
            )
        self.api_key = api_key

    # ---------- Generic GET ----------

    def _get(self, params: dict[str, Any]) -> dict:
        params = {**params, "api_key": self.api_key}
        try:
            r = requests.get(API_URL, params=params, timeout=TIMEOUT)
        except requests.RequestException as e:
            log.error("SerpAPI request failed: %s", e)
            return {}

        if r.status_code != 200:
            log.error("SerpAPI HTTP %s: %s", r.status_code, r.text[:300])
            return {}

        try:
            return r.json()
        except ValueError:
            log.error("SerpAPI returned non-JSON: %s", r.text[:300])
            return {}

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
        gl: str = "in",
        hl: str = "en",
    ) -> list[FlightOffer]:
        params: dict[str, Any] = {
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": destination,
            "outbound_date": departure_date,
            "adults": adults,
            "currency": currency,
            "travel_class": _TRAVEL_CLASS_MAP.get(travel_class.upper(), 1),
            "type": 1 if return_date else 2,   # 1=round, 2=one-way
            "gl": gl,
            "hl": hl,
        }
        if return_date:
            params["return_date"] = return_date

        data = self._get(params)
        if not data:
            return []
        if "error" in data:
            log.error("SerpAPI error: %s", data["error"])
            return []

        # 'best_flights' often contains the curated cheapest options;
        # fall back to 'other_flights' if best is empty.
        raw_offers = data.get("best_flights") or data.get("other_flights") or []
        offers: list[FlightOffer] = []
        for raw in raw_offers[:max_results]:
            try:
                offers.append(self._parse_flight(raw, currency))
            except Exception as e:  # noqa: BLE001
                log.warning("Skipping malformed flight offer: %s", e)
        offers.sort(key=lambda o: o.price)
        return offers

    @staticmethod
    def _parse_flight(raw: dict, fallback_cur: str) -> FlightOffer:
        price = float(raw["price"])
        # SerpAPI doesn't always include explicit currency in the offer block;
        # the parent search uses the requested currency.
        flights = raw.get("flights", [])
        first = flights[0] if flights else {}
        last = flights[-1] if flights else {}
        airline = first.get("airline", "Unknown")
        dep_time = first.get("departure_airport", {}).get("time", "")
        arr_time = last.get("arrival_airport", {}).get("time", "")
        duration_minutes = int(raw.get("total_duration", 0) or 0)
        stops = max(0, len(flights) - 1)
        return FlightOffer(
            price=price,
            currency=fallback_cur,
            airline=airline,
            departure_time=dep_time,
            arrival_time=arr_time,
            duration_minutes=duration_minutes,
            stops=stops,
        )

    # ---------- Hotels ----------

    def search_hotels(
        self,
        query: str,
        check_in: str,
        check_out: str,
        adults: int = 2,
        currency: str = "INR",
        max_results: int = 10,
        gl: str = "in",
        hl: str = "en",
    ) -> list[HotelOffer]:
        params: dict[str, Any] = {
            "engine": "google_hotels",
            "q": query,
            "check_in_date": check_in,
            "check_out_date": check_out,
            "adults": adults,
            "currency": currency,
            "gl": gl,
            "hl": hl,
        }
        data = self._get(params)
        if not data:
            return []
        if "error" in data:
            log.error("SerpAPI hotels error: %s", data["error"])
            return []

        properties = data.get("properties", [])
        offers: list[HotelOffer] = []
        for raw in properties[:max_results]:
            try:
                offers.append(self._parse_hotel(raw, check_in, check_out, currency))
            except Exception as e:  # noqa: BLE001
                log.warning("Skipping malformed hotel: %s", e)

        offers = [o for o in offers if o.total_price > 0]
        offers.sort(key=lambda o: o.total_price)
        return offers

    @staticmethod
    def _parse_hotel(raw: dict, ci: str, co: str, fallback_cur: str) -> HotelOffer:
        name = raw.get("name", "Unknown")
        rating = raw.get("overall_rating")
        property_token = raw.get("property_token", "")

        # Total price for the stay
        total = 0.0
        total_block = raw.get("total_rate") or {}
        rate_block = raw.get("rate_per_night") or {}
        if "extracted_lowest" in total_block:
            total = float(total_block["extracted_lowest"])
        elif "extracted_lowest" in rate_block:
            # Fall back to per-night × nights estimated as 1 if we can't compute.
            total = float(rate_block["extracted_lowest"])

        return HotelOffer(
            hotel_name=name,
            total_price=total,
            currency=fallback_cur,
            check_in=ci,
            check_out=co,
            rating=float(rating) if rating is not None else None,
            hotel_id=property_token,
        )
