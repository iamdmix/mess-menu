"""Mess Menu API.

Serves the mess menu for the current or next requested meal, based on
Asia/Kolkata (IST) wall-clock time.

``GET /meal`` returns the serving or next-upcoming meal. ``GET /meal?meal=X``
returns the next occurrence of meal X: today's serving while its window is
still open (before or during), otherwise tomorrow's. The ``text`` field is a
speech-friendly English sentence (e.g. "Thursday's snacks are ...") meant to be
read aloud by Siri.

Menu data lives in ``menu.json`` and is re-read on every request. Entries are
keyed by exact calendar date (``YYYY-MM-DD``); a weekday-name key
(``monday``..``sunday``) is used as a fallback when a specific date is not
covered.
"""

import datetime as dt
import json
import os
import re
from enum import Enum
from pathlib import Path

import pytz
from fastapi import FastAPI, HTTPException, Response

IST = pytz.timezone("Asia/Kolkata")
MENU_PATH = Path(os.environ.get("MENU_PATH", Path(__file__).resolve().parent / "menu.json"))

# Parenthesised quantities ("(2 no.s)", "(1 no.)", "(2 medium size)") read
# badly over Siri. Drop any parenthetical containing a digit; keep descriptive
# ones like "(Alternate Week)".
_QUANTITY_RE = re.compile(r"\s*\((?=[^)]*\d)[^)]*\)")

app = FastAPI(
    title="Mess Menu API",
    description="Current or next-upcoming mess meal, with IST meal-timing rules.",
    version="1.2.0",
)


class Meal(str, Enum):
    breakfast = "breakfast"
    lunch = "lunch"
    snacks = "snacks"
    dinner = "dinner"


MEAL_ORDER = [m.value for m in Meal]

# Meal windows in minutes since midnight, IST. Start inclusive, end exclusive.
WEEKDAY_SLOTS = {
    "breakfast": (7 * 60, 9 * 60),            # 07:00 - 09:00
    "lunch": (12 * 60, 14 * 60),              # 12:00 - 14:00
    "snacks": (17 * 60, 18 * 60 + 30),        # 17:00 - 18:30
    "dinner": (19 * 60, 21 * 60),             # 19:00 - 21:00
}
WEEKEND_SLOTS = {
    "breakfast": (7 * 60 + 30, 9 * 60 + 30),  # 07:30 - 09:30
    "lunch": (12 * 60 + 30, 14 * 60 + 30),    # 12:30 - 14:30
    "snacks": (17 * 60, 18 * 60 + 30),        # 17:00 - 18:30
    "dinner": (19 * 60, 21 * 60),             # 19:00 - 21:00
}


def load_menu() -> dict:
    try:
        with open(MENU_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="menu.json not found")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"menu.json is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="menu.json must be a JSON object")
    return data


def slots_for_date(d: dt.date) -> dict:
    """Sat/Sun use the weekend timings, everything else weekday timings."""
    return WEEKEND_SLOTS if d.weekday() >= 5 else WEEKDAY_SLOTS


def select_meal(d: dt.date, at: dt.datetime) -> tuple[str, dt.date]:
    """Pick the active or next upcoming meal for date ``d`` at IST time ``at``.

    Returns ``(meal, serving_date)``. Inside a window -> that meal on ``d``.
    Between windows -> the next meal starting on ``d``. After the dinner
    window -> ``breakfast`` of the following day.
    """
    minutes = at.hour * 60 + at.minute
    slots = slots_for_date(d)

    for meal in MEAL_ORDER:
        start, end = slots[meal]
        if start <= minutes < end:
            return meal, d

    for meal in MEAL_ORDER:
        if minutes < slots[meal][0]:
            return meal, d

    return "breakfast", d + dt.timedelta(days=1)


def next_meal_date(meal: str, now: dt.datetime) -> dt.date:
    """Serving date for an explicit meal request.

    Today if that meal's window on today's schedule hasn't ended yet (serving
    now or still upcoming), otherwise tomorrow. E.g. asking for breakfast on a
    Thursday evening returns Friday's breakfast.
    """
    minutes = now.hour * 60 + now.minute
    end = slots_for_date(now.date())[meal][1]
    return now.date() if minutes < end else now.date() + dt.timedelta(days=1)


def resolve_entry(menu: dict, d: dt.date) -> dict | None:
    """Exact date key first, weekday-name key as fallback."""
    for key in (d.isoformat(), d.strftime("%A").lower()):
        entry = menu.get(key)
        if isinstance(entry, dict):
            return entry
    return None


def clean_items(raw) -> str:
    """Speech-friendly item list: quantity counts stripped, single spacing."""
    if not isinstance(raw, str):
        raw = "" if raw is None else str(raw)
    return " ".join(_QUANTITY_RE.sub("", raw).split())


def build_payload(menu: dict, serving_date: dt.date, meal: str) -> dict:
    entry = resolve_entry(menu, serving_date) or {}
    items = clean_items(entry.get(meal, ""))

    day_label = entry.get("day")
    if not (isinstance(day_label, str) and day_label.strip()):
        day_label = serving_date.strftime("%A")
    day_label = day_label.strip().title()

    if items:
        verb = "are" if meal == "snacks" else "is"
        text = f"{day_label}'s {meal} {verb} {items}"
    else:
        text = f"{day_label}'s {meal} menu is not available yet"

    return {
        "day": day_label,
        "meal": meal.capitalize(),
        "items": items,
        "text": text,
    }


@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/meal")
def get_meal(
    response: Response,
    meal: Meal | None = None,
) -> dict:
    """Return the current/upcoming meal, or the next occurrence of one meal.

    - No params: auto-select from the current IST time — the meal being served
      now, else the next upcoming one; after the dinner window it rolls to
      tomorrow's breakfast.
    - ``meal``: next occurrence of that meal — today's while its window is
      still open (before or during), otherwise tomorrow's (asking for
      breakfast on a Thursday evening returns Friday's breakfast).
    """
    response.headers["Cache-Control"] = "no-store"
    menu = load_menu()
    now = dt.datetime.now(IST)

    if meal is not None:
        meal_name = meal.value
        serving_date = next_meal_date(meal_name, now)
    else:
        meal_name, serving_date = select_meal(now.date(), now)

    return build_payload(menu, serving_date, meal_name)
