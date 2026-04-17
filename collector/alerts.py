"""
Open GitHub Issues for price-drop alerts.

Uses GITHUB_TOKEN (auto-injected in Actions) and GITHUB_REPOSITORY
(auto-injected, format "owner/repo"). No external auth needed.
Falls back to printing to stdout if either env var is missing
(useful when testing locally).
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

GH_API = "https://api.github.com"


def open_issue(title: str, body: str, labels: list[str] | None = None) -> bool:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")  # "owner/repo"

    if not token or not repo:
        log.info("[ALERT - would open issue]\n%s\n\n%s", title, body)
        return False

    url = f"{GH_API}/repos/{repo}/issues"
    payload = {
        "title": title,
        "body": body,
        "labels": labels or ["price-alert"],
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    r = requests.post(url, json=payload, headers=headers, timeout=30)
    if r.status_code in (200, 201):
        log.info("Opened issue: %s", title)
        return True
    log.error("Failed to open issue (%s): %s", r.status_code, r.text)
    return False


def flight_alert(search: dict, price: float, prev_min: float | None) -> None:
    sid = search["id"]
    nick = search.get("nickname", sid)
    threshold = search["alert_below"]
    cur = search.get("currency", "INR")
    prev_str = f"{prev_min:,.0f} {cur}" if prev_min else "n/a"
    title = f"✈️ Flight price drop: {nick} — {price:,.0f} {cur}"
    body = (
        f"**Search:** `{sid}` — {nick}\n"
        f"**Route:** {search['origin']} → {search['destination']}\n"
        f"**Dates:** {search['departure_date']}"
        + (f" / return {search['return_date']}" if search.get('return_date') else "")
        + f"\n\n"
        f"**New low:** {price:,.0f} {cur}\n"
        f"**Previous min:** {prev_str}\n"
        f"**Your alert threshold:** {threshold:,.0f} {cur}\n\n"
        f"_Open the dashboard for full history._"
    )
    open_issue(title, body, labels=["price-alert", "flights"])


def hotel_alert(search: dict, price: float, hotel_name: str, prev_min: float | None) -> None:
    sid = search["id"]
    nick = search.get("nickname", sid)
    threshold = search["alert_below"]
    cur = search.get("currency", "INR")
    prev_str = f"{prev_min:,.0f} {cur}" if prev_min else "n/a"
    title = f"🏨 Hotel price drop: {nick} — {price:,.0f} {cur}"
    body = (
        f"**Search:** `{sid}` — {nick}\n"
        f"**Hotel:** {hotel_name}\n"
        f"**City:** {search['city_code']}\n"
        f"**Dates:** {search['check_in']} → {search['check_out']}\n\n"
        f"**New low:** {price:,.0f} {cur}\n"
        f"**Previous min:** {prev_str}\n"
        f"**Your alert threshold:** {threshold:,.0f} {cur}\n\n"
        f"_Open the dashboard for full history._"
    )
    open_issue(title, body, labels=["price-alert", "hotels"])
