"""
Daily collector entry point.

Reads searches.yaml, calls SerpAPI for each, appends results to CSVs,
fires alerts for price drops, and (re)generates the dashboard HTML.

Run locally:
    SERPAPI_KEY=... python -m collector.collect

In GitHub Actions, env vars come from repo secrets.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime

import yaml

from collector import alerts, dashboard, storage
from collector.serpapi_client import SerpApiClient

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("collect")

ROOT = os.path.dirname(os.path.dirname(__file__))
SEARCHES_PATH = os.path.join(ROOT, "searches.yaml")


def load_searches() -> dict:
    with open(SEARCHES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def is_future(d: str) -> bool:
    try:
        return datetime.strptime(d, "%Y-%m-%d").date() >= date.today()
    except ValueError:
        return False


def _previous_min(rows: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in rows:
        sid = r.get("search_id")
        if not sid:
            continue
        try:
            p = float(r["price"])
        except (KeyError, ValueError):
            continue
        if sid not in out or p < out[sid]:
            out[sid] = p
    return out


def collect_flights(client: SerpApiClient, searches: list[dict]) -> None:
    if not searches:
        return
    prev_min = _previous_min(storage.read_flights())
    ts = storage.now_iso()

    for s in searches:
        sid = s["id"]
        if not is_future(s["outbound_date"]):
            log.warning("Skipping %s — outbound date in past: %s", sid, s["outbound_date"])
            continue
        if s.get("return_date") and not is_future(s["return_date"]):
            log.warning("Skipping %s — return date in past: %s", sid, s["return_date"])
            continue

        log.info("Querying flight: %s (%s → %s)", sid, s["departure_id"], s["arrival_id"])
        offers = client.search_flights(
            origin=s["departure_id"],
            destination=s["arrival_id"],
            departure_date=s["outbound_date"],
            return_date=s.get("return_date"),
            adults=s.get("adults", 1),
            travel_class=s.get("travel_class", "ECONOMY"),
            currency=s.get("currency", "INR"),
            max_results=s.get("max_results", 5),
            gl=s.get("gl", "in"),
            hl=s.get("hl", "en"),
        )
        if not offers:
            log.warning("  no offers returned")
            continue

        rows = []
        for rank, o in enumerate(offers, start=1):
            rows.append({
                "timestamp": ts,
                "search_id": sid,
                "nickname": s.get("nickname", sid),
                "origin": s["departure_id"],
                "destination": s["arrival_id"],
                "departure_date": s["outbound_date"],
                "return_date": s.get("return_date", ""),
                "rank": rank,
                "price": f"{o.price:.2f}",
                "currency": o.currency,
                "airline": o.airline,
                "stops": o.stops,
                "duration_minutes": o.duration_minutes,
                "departure_time": o.departure_time,
                "arrival_time": o.arrival_time,
            })
        storage.append_flight_rows(rows)
        log.info("  saved %d offers (cheapest: %.2f %s)",
                 len(rows), offers[0].price, offers[0].currency)

        cheapest = offers[0].price
        threshold = s.get("alert_below")
        if threshold and cheapest < threshold and (sid not in prev_min or cheapest < prev_min[sid]):
            alerts.flight_alert({
                "id": sid,
                "nickname": s.get("nickname", sid),
                "origin": s["departure_id"],
                "destination": s["arrival_id"],
                "departure_date": s["outbound_date"],
                "return_date": s.get("return_date"),
                "alert_below": threshold,
                "currency": s.get("currency", "INR"),
            }, cheapest, prev_min.get(sid))


def collect_hotels(client: SerpApiClient, searches: list[dict]) -> None:
    if not searches:
        return
    prev_min = _previous_min(storage.read_hotels())
    ts = storage.now_iso()

    for s in searches:
        sid = s["id"]
        if not is_future(s["check_in"]):
            log.warning("Skipping %s — check-in in past: %s", sid, s["check_in"])
            continue

        log.info("Querying hotels: %s (q=%r)", sid, s["query"])
        offers = client.search_hotels(
            query=s["query"],
            check_in=s["check_in"],
            check_out=s["check_out"],
            adults=s.get("adults", 2),
            currency=s.get("currency", "INR"),
            max_results=s.get("max_results", 10),
            gl=s.get("gl", "in"),
            hl=s.get("hl", "en"),
        )
        if not offers:
            log.warning("  no hotel offers returned")
            continue

        rows = []
        for rank, o in enumerate(offers, start=1):
            rows.append({
                "timestamp": ts,
                "search_id": sid,
                "nickname": s.get("nickname", sid),
                "city_code": s.get("query", "")[:60],
                "check_in": s["check_in"],
                "check_out": s["check_out"],
                "rank": rank,
                "hotel_id": o.hotel_id,
                "hotel_name": o.hotel_name,
                "price": f"{o.total_price:.2f}",
                "currency": o.currency,
                "room_type": f"★ {o.rating}" if o.rating else "",
            })
        storage.append_hotel_rows(rows)
        cheapest = offers[0]
        log.info("  saved %d offers (cheapest: %.2f %s @ %s)",
                 len(rows), cheapest.total_price, cheapest.currency, cheapest.hotel_name)

        threshold = s.get("alert_below")
        if threshold and cheapest.total_price < threshold and (sid not in prev_min or cheapest.total_price < prev_min[sid]):
            alerts.hotel_alert({
                "id": sid,
                "nickname": s.get("nickname", sid),
                "city_code": s.get("query", ""),
                "check_in": s["check_in"],
                "check_out": s["check_out"],
                "alert_below": threshold,
                "currency": s.get("currency", "INR"),
            }, cheapest.total_price, cheapest.hotel_name, prev_min.get(sid))


def main() -> int:
    log.info("Travel price tracker starting…")
    cfg = load_searches()
    flights = cfg.get("flights") or []
    hotels = cfg.get("hotels") or []
    log.info("Loaded %d flight searches and %d hotel searches",
             len(flights), len(hotels))

    if not flights and not hotels:
        log.warning("No searches configured. Edit searches.yaml.")
        return 0

    try:
        client = SerpApiClient()
    except RuntimeError as e:
        log.error(str(e))
        return 1

    collect_flights(client, flights)
    collect_hotels(client, hotels)

    log.info("Generating dashboard…")
    dashboard.generate()
    log.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
