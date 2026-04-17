"""
CSV storage. One file per data type, append-only.
Schema is fixed so the dashboard and analyzer can rely on it.
"""

from __future__ import annotations

import csv
import os
from collections.abc import Iterable
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

FLIGHTS_CSV = os.path.join(DATA_DIR, "prices_flights.csv")
HOTELS_CSV = os.path.join(DATA_DIR, "prices_hotels.csv")

FLIGHT_COLS = [
    "timestamp",
    "search_id",
    "nickname",
    "origin",
    "destination",
    "departure_date",
    "return_date",
    "rank",        # 1 = cheapest, 2 = next, ...
    "price",
    "currency",
    "airline",
    "stops",
    "duration_minutes",
    "departure_time",
    "arrival_time",
]

HOTEL_COLS = [
    "timestamp",
    "search_id",
    "nickname",
    "city_code",
    "check_in",
    "check_out",
    "rank",
    "hotel_id",
    "hotel_name",
    "price",
    "currency",
    "room_type",
]


def _ensure(path: str, header: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_flight_rows(rows: Iterable[dict]) -> int:
    _ensure(FLIGHTS_CSV, FLIGHT_COLS)
    n = 0
    with open(FLIGHTS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FLIGHT_COLS, extrasaction="ignore")
        for row in rows:
            w.writerow(row)
            n += 1
    return n


def append_hotel_rows(rows: Iterable[dict]) -> int:
    _ensure(HOTELS_CSV, HOTEL_COLS)
    n = 0
    with open(HOTELS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HOTEL_COLS, extrasaction="ignore")
        for row in rows:
            w.writerow(row)
            n += 1
    return n


def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_flights() -> list[dict]:
    return read_csv(FLIGHTS_CSV)


def read_hotels() -> list[dict]:
    return read_csv(HOTELS_CSV)
