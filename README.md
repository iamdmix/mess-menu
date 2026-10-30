# 🍛 Mess Menu API

[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com)
[![Cloudflare Tunnel](https://img.shields.io/badge/Cloudflare-Tunnel-F38020?logo=cloudflare&logoColor=white)](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)

A tiny FastAPI microservice that serves my hostel mess menu on IST
(Asia/Kolkata) clock logic, publicly at
**[meal.dharmikshinde.in/meal](https://meal.dharmikshinde.in/meal)** — so
Siri, Shortcuts and my dashboard always know what's cooking. Runs on my
homelab (Intel Mac, OrbStack/Docker), exposed via a Cloudflare Tunnel.

## Why this exists

Hostel mess menus are ugly PDFs that change every week. This service takes
one `menu.json` and answers the only question that matters, in plain English:

> _"What's for dinner?"_

— answered down to the minute, including "you're past lunch, next is snacks
at 5 PM" or "…no wait, lunch is over — tomorrow's breakfast is at 07:00".

## ✨ Features

- **Serving-or-next logic** — the meal being served right now, or the next
  one up (correct across day boundaries, IST throughout)
- **Weekday/weekend timing** — separate meal windows for Mon–Fri and Sat–Sun
- **Speech-friendly `text` field** — pre-written to sound right when read aloud by Siri
- **Quantity stripping** — `(2 no.s)` stripped from responses (kept in
  `menu.json`); descriptive parens like `(Alternate Week)` preserved
- **Hot-reload** — `menu.json` is bind-mounted and re-read on every request;
  menu edits need no restart
- **Backup-and-apply pipeline** — validate → timestamped backup → write →
  restart → health-check, one script
- **Healthcheck** — built into the container compose

## 🚀 Quick start

```bash
git clone https://github.com/iamdmix/mess-menu.git
cd mess-menu
docker compose up -d --build

curl http://localhost:8085/meal | jq
```

Service is live at `http://localhost:8085`; every wall-clock rule is Asia/Kolkata.

## 📡 Endpoints

| Route | Description |
|---|---|
| `GET /meal` | Serving now, else the next upcoming meal (after dinner → tomorrow's breakfast) |
| `GET /meal?meal=breakfast` | Next occurrence of that meal: today while its window is still open, else tomorrow |
| `GET /meal?meal=lunch` | Same rule for `lunch` / `snacks` / `dinner` |
| `GET /health` | Liveness probe |

**Response** (Apple Shortcuts / Siri friendly — `text` is a plain sentence):

```json
{
  "day": "Friday",
  "meal": "Dinner",
  "items": "Jeera Rice, Rajma Masala, Boondi Raita, Papad, Gulab Jamun",
  "text": "Friday's dinner is Jeera Rice, Rajma Masala, Raita, Papad, Gulab Jamun"
}
```

`text` is the Siri-ready one-liner; `items` is the same list; `day` and
`meal` are there for Shortcuts that want extra logic.

### ⏰ Timing rules (IST)

| Meal | Weekdays (Mon–Fri) | Weekends (Sat–Sun) |
|---|---|---|
| Breakfast | 07:00 – 09:00 | 07:30 – 09:30 |
| Lunch | 12:00 – 14:00 | 12:30 – 14:30 |
| Snacks | 17:00 – 18:30 | 17:00 – 18:30 |
| Dinner | 19:00 – 21:00 | 19:00 – 21:00 |

Start times inclusive, end times exclusive. Menu lookup: the exact
`YYYY-MM-DD` key of the serving date first; weekday-name (`monday`…`sunday`)
as the fallback when a date isn't covered.

## 📲 iOS Shortcuts — "Hey Siri, what's for dinner?"

> The **whole point** of the `text` field. Build this once, never wonder again:

1. Open the **Shortcuts** app → **+** (new shortcut)
2. Add action → **URL** → paste `https://meal.dharmikshinde.in/meal`
3. Add action → **Get Contents of URL**
4. Add action → **Get Dictionary Value** → key `text`
5. Add action → **Speak Text**
6. Tap ⓘ (info) → **Add to Siri** → record *"What's for dinner?"*

Done. From now on: *"Hey Siri, what's for dinner?"* — it fetches this API
and reads the current/next meal aloud.

Variations:

- **Another meal:** same steps, change the URL to `/meal?meal=lunch`
  (or `breakfast` / `snacks` / `dinner`) and name the shortcut accordingly
- **Silent version:** skip **Speak Text**, add **Show Result** instead —
  glanceable card, no voice
- **One-tap widget:** pin this shortcut as a Shortcuts home-screen or
  lock-screen widget

## 🔄 Updating the menu

- **Via Telegram** (primary): send the new menu photo/PDF to my Hermes bot
  with a caption like *"update mess menu"* (or paste raw JSON) — it
  transcribes, validates, backs up, writes, restarts and verifies automatically.
- **Manually:**

  ```bash
  python3 scripts/apply_menu.py new_menu.json
  ```

  Accepts date-keyed and/or weekday-keyed menus; adds a timestamped copy to
  `backups/`, restarts the container, health-checks it.

`menu.json` schema:

```json
{
  "2026-09-19": {"day": "Saturday", "breakfast": "...", "lunch": "...", "snacks": "...", "dinner": "..."},
  "monday":     {"breakfast": "...", "lunch": "...", "snacks": "...", "dinner": "..."}
}
```

Missing meals → `""`. The service re-reads the file on every request — no
restart needed for menu changes (restart only after code changes).

## 🧰 Ops

```bash
cd ~/services/mess-menu
docker compose up -d --build     # build / rebuild after code changes
docker restart mess-menu         # pick up code changes
docker logs --tail 50 mess-menu  # tail logs
curl -s localhost:8085/meal | jq # quick manual check
```

Timing tests live in-container:

```bash
docker exec -i mess-menu python - < scripts/test_timing.py
```

## 📁 Layout

```
main.py                 FastAPI app (IST logic, /meal, /health)
menu.json               Live menu keyed by date (bind-mounted into the container)
Dockerfile              python:3.11-slim + uvicorn
docker-compose.yml      port 8085 -> 8000, restart unless-stopped, healthcheck
scripts/apply_menu.py   validate -> backup -> write -> restart -> verify
scripts/test_timing.py  in-container timing + lookup + speech-text tests
backups/                timestamped menu.json snapshots
```

## 🔭 Ideas / TODO

- [ ] Telegram bot command `/menu` hitting this API (via the Hermes agent)
- [ ] ntfy/GameBar push 10 min before each meal window opens
- [ ] `/full` — full-week menu as a simple HTML table

## 📄 License

MIT
