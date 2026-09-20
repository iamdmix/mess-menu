#!/usr/bin/env python3
"""Timing, next-occurrence and speech-text tests for the mess-menu app.

Run inside the container:

    docker exec -i mess-menu python - < scripts/test_timing.py
"""

import sys
from datetime import date, datetime

import main  # /app is the working directory inside the container

failures = 0
total = 0


def check(label: str, got, expected) -> None:
    global failures, total
    total += 1
    ok = got == expected
    failures += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  {label} -> {got!r}  (expected {expected!r})")


def at(hhmm: str, d: date = date(2026, 9, 17)):
    hh, mm = (int(part) for part in hhmm.split(":"))
    return main.IST.localize(datetime(d.year, d.month, d.day, hh, mm))


# --- select_meal: auto-selection (no meal param) ------------------------------

for d, hhmm, exp_meal, exp_date in [
    (date(2026, 9, 17), "06:30", "breakfast", date(2026, 9, 17)),
    (date(2026, 9, 17), "08:00", "breakfast", date(2026, 9, 17)),
    (date(2026, 9, 17), "13:00", "lunch", date(2026, 9, 17)),
    (date(2026, 9, 17), "15:00", "snacks", date(2026, 9, 17)),
    (date(2026, 9, 17), "18:45", "dinner", date(2026, 9, 17)),
    (date(2026, 9, 17), "22:00", "breakfast", date(2026, 9, 18)),
    (date(2026, 9, 18), "09:00", "lunch", date(2026, 9, 18)),
    (date(2026, 9, 19), "08:00", "breakfast", date(2026, 9, 19)),
    (date(2026, 9, 19), "09:00", "breakfast", date(2026, 9, 19)),
    (date(2026, 9, 19), "09:45", "lunch", date(2026, 9, 19)),
    (date(2026, 9, 20), "22:30", "breakfast", date(2026, 9, 21)),
]:
    check(f"select_meal {d} {hhmm}", main.select_meal(d, at(hhmm, d)), (exp_meal, exp_date))


# --- next_meal_date: explicit meal requests (today while open, else tomorrow) --

for hhmm, meal, exp_date in [
    ("06:30", "breakfast", date(2026, 9, 17)),  # before window -> today
    ("08:00", "breakfast", date(2026, 9, 17)),  # during window -> today
    ("09:00", "breakfast", date(2026, 9, 18)),  # window ended -> tomorrow
    ("13:00", "lunch", date(2026, 9, 17)),      # during lunch -> today
    ("15:00", "lunch", date(2026, 9, 18)),      # after lunch -> tomorrow
    ("08:00", "snacks", date(2026, 9, 17)),     # snacks later today -> today
    ("20:00", "dinner", date(2026, 9, 17)),     # during dinner -> today
    ("22:00", "dinner", date(2026, 9, 18)),     # after dinner -> tomorrow
]:
    check(f"next_meal_date {hhmm} {meal}", main.next_meal_date(meal, at(hhmm)), exp_date)


# --- clean_items: quantity counts stripped, descriptions kept ------------------

for raw, expected in [
    ("Banana bhaji (2 no.s), Chutney, Tea", "Banana bhaji, Chutney, Tea"),
    ("Boiled Egg (2 Nos), BBJ", "Boiled Egg, BBJ"),
    ("Veg Puffs (1 no.) / Veg Sandwich (Alternate Week), Sauce",
     "Veg Puffs / Veg Sandwich (Alternate Week), Sauce"),
    ("Onion Samosa (2 medium size), Tea", "Onion Samosa, Tea"),
    ("Ice Cream (VANILLA/CHOCOLATE)-Alternate Week", "Ice Cream (VANILLA/CHOCOLATE)-Alternate Week"),
]:
    check(f"clean_items {raw[:28]!r}", main.clean_items(raw), expected)


# --- build_payload: lookup order + speech text ---------------------------------

MENU = {
    "2026-09-17": {"day": "Thursday", "breakfast": "A", "lunch": "B", "snacks": "C (2 no.s)", "dinner": "D"},
    "monday": {"breakfast": "MA", "lunch": "MB", "snacks": "MC", "dinner": "MD"},
}
for d, meal, exp_items, exp_text in [
    (date(2026, 9, 17), "lunch", "B", "Thursday's lunch is B"),
    (date(2026, 9, 17), "snacks", "C", "Thursday's snacks are C"),
    (date(2026, 9, 21), "lunch", "MB", "Monday's lunch is MB"),
    (date(2026, 9, 22), "lunch", "", "Tuesday's lunch menu is not available yet"),
]:
    payload = main.build_payload(MENU, d, meal)
    check(f"build_payload {d} {meal}", (payload["items"], payload["text"]), (exp_items, exp_text))

print(f"\n{total - failures}/{total} passed")
sys.exit(1 if failures else 0)
