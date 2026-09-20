#!/usr/bin/env python3
"""Apply a new mess menu to the mess-menu service.

Pipeline: validate -> timestamped backup -> write menu.json in place ->
docker restart -> health check -> sample the API.

Menu entries may be keyed by exact date (``YYYY-MM-DD``) and/or by weekday
name (``monday``..``sunday``).

Usage:
  python3 scripts/apply_menu.py /path/to/new_menu.json
  python3 scripts/apply_menu.py -            # read new menu JSON from stdin

Exit codes: 0 ok, 2 validation/input error, 3 docker restart failed,
4 service did not become healthy.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent.parent
MENU_PATH = SERVICE_DIR / "menu.json"
BACKUP_DIR = SERVICE_DIR / "backups"
CONTAINER = "mess-menu"
BASE_URL = "http://127.0.0.1:8085"

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MEALS = ["breakfast", "lunch", "snacks", "dinner"]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def die(msg: str, code: int = 2):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_new_menu(source: str) -> dict:
    try:
        raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    except OSError as exc:
        die(f"cannot read new menu: {exc}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        die(f"new menu is not valid JSON: {exc}")
    if not isinstance(data, dict):
        die("new menu must be a JSON object")
    return data


def _clean_text(value, label: str) -> str:
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        die(f"'{label}' must be a string")
    return " ".join(value.split())  # collapse stray whitespace


def validate(data: dict) -> dict:
    """Accept date-keyed entries (YYYY-MM-DD) and/or weekday-keyed ones."""
    if not data:
        die("menu must be a non-empty JSON object")
    clean: dict = {}
    date_count = 0
    weekday_count = 0
    for key, value in data.items():
        if not isinstance(value, dict):
            die(f"'{key}' must be an object with the meal keys")
        if DATE_RE.match(str(key)):
            try:
                date.fromisoformat(key)
            except ValueError:
                die(f"'{key}' is not a valid calendar date")
            missing = [m for m in MEALS if m not in value]
            if missing:
                die(f"'{key}' is missing: {', '.join(missing)}")
            unknown = [k for k in value if k not in set(MEALS) | {"day"}]
            if unknown:
                die(f"'{key}' has unknown keys: {', '.join(unknown)}")
            entry = {m: _clean_text(value[m], f"{key}.{m}") for m in MEALS}
            if "day" in value:
                entry["day"] = _clean_text(value["day"], f"{key}.day")
            clean[key] = entry
            date_count += 1
        elif key in DAYS:
            missing = [m for m in MEALS if m not in value]
            if missing:
                die(f"'{key}' is missing: {', '.join(missing)}")
            unknown = [k for k in value if k not in MEALS]
            if unknown:
                die(f"'{key}' has unknown keys: {', '.join(unknown)}")
            clean[key] = {m: _clean_text(value[m], f"{key}.{m}") for m in MEALS}
            weekday_count += 1
        else:
            die(f"unknown key '{key}' - expected YYYY-MM-DD or a weekday name")
    print(f"validated: {date_count} date entries, {weekday_count} weekday entries")
    return clean


def http_get(path: str, timeout: float = 5.0):
    with urllib.request.urlopen(BASE_URL + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("menu_file", help="path to the new menu JSON ('-' for stdin)")
    parser.add_argument("--skip-restart", action="store_true", help="write + backup only")
    args = parser.parse_args()

    data = validate(load_new_menu(args.menu_file))

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if MENU_PATH.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = BACKUP_DIR / f"menu-{stamp}.json"
        shutil.copy2(MENU_PATH, backup)
        print(f"backup: {backup}")
    else:
        print("backup: skipped (no existing menu.json)")

    # Truncate + write in place: keeps the inode so the container's bind
    # mount always sees the fresh content.
    MENU_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"written: {MENU_PATH} ({MENU_PATH.stat().st_size} bytes)")

    if args.skip_restart:
        print("restart: skipped (--skip-restart)")
    else:
        proc = subprocess.run(["docker", "restart", CONTAINER], capture_output=True, text=True)
        if proc.returncode != 0:
            die(f"docker restart failed: {proc.stderr.strip() or proc.stdout.strip()}", code=3)
        print(f"restart: {proc.stdout.strip()}")

        deadline = time.time() + 30
        last_err: object = None
        while time.time() < deadline:
            try:
                if http_get("/health").get("status") == "ok":
                    break
            except Exception as exc:  # retry loop
                last_err = exc
            time.sleep(1)
        else:
            die(f"service did not become healthy within 30s ({last_err})", code=4)
        print("health: ok")

    try:
        sample = http_get("/meal")
        print("now serving: " + json.dumps(sample, ensure_ascii=False))
    except Exception as exc:
        print(f"note: could not fetch /meal sample ({exc})")

    print("OK: menu applied")


if __name__ == "__main__":
    main()
