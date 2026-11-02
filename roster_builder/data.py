"""Load the fictional CSVs and the sample rules."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
AREAS = ("front", "kitchen")

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def _cents(dollars: str) -> int:
    whole, _, frac = dollars.strip().partition(".")
    frac = (frac + "00")[:2]
    sign = -1 if whole.startswith("-") else 1
    whole = whole.lstrip("-") or "0"
    return sign * (int(whole) * 100 + int(frac))


def _hours(value: str) -> int:
    return int(value) * 60


@dataclass(frozen=True)
class Rules:
    venue: str
    disclaimer: str
    cost_note: str
    min_shift_minutes: int
    meal_break_after_minutes: int
    meal_break_minutes: int
    min_rest_minutes: int
    max_week_minutes_cap: int
    open_hour: int
    close_hour: int
    front_entries_per_person: int
    max_front: int
    kitchen_quiet_below: int
    kitchen_second_from: int
    weekly_labour_budget_cents: int


@dataclass(frozen=True)
class Staff:
    id: str
    name: str
    area: str
    can_open: bool
    can_close: bool
    max_minutes: int
    rate_cents: int
    windows: dict[str, tuple[int, int]] = field(hash=False, compare=False)


@dataclass(frozen=True)
class Shift:
    staff_id: str
    day: str
    start: int
    end: int
    break_minutes: int = 0

    def span_minutes(self) -> int:
        return (self.end - self.start) * 60

    def paid_minutes(self) -> int:
        return max(0, self.span_minutes() - self.break_minutes)


@dataclass
class Venue:
    rules: Rules
    staff: list[Staff]
    traffic: dict[tuple[str, int], int]
    hours: list[int]

    def staff_by_id(self) -> dict[str, Staff]:
        return {person.id: person for person in self.staff}

    def cap_minutes(self, person: Staff) -> int:
        return min(person.max_minutes, self.rules.max_week_minutes_cap)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def load_rules(path: Path | None = None) -> Rules:
    raw = json.loads((path or DATA_DIR / "rules.json").read_text())
    return Rules(
        venue=raw["venue"],
        disclaimer=raw["disclaimer"],
        cost_note=raw["cost_note"],
        min_shift_minutes=_hours(str(raw["min_shift_hours"])),
        meal_break_after_minutes=_hours(str(raw["meal_break_after_hours"])),
        meal_break_minutes=int(raw["meal_break_minutes"]),
        min_rest_minutes=_hours(str(raw["min_rest_hours"])),
        max_week_minutes_cap=_hours(str(raw["max_week_hours_cap"])),
        open_hour=int(raw["open_hour"]),
        close_hour=int(raw["close_hour"]),
        front_entries_per_person=int(raw["front_entries_per_person"]),
        max_front=int(raw["max_front"]),
        kitchen_quiet_below=int(raw["kitchen_quiet_below"]),
        kitchen_second_from=int(raw["kitchen_second_from"]),
        weekly_labour_budget_cents=_cents(f"{float(raw['weekly_labour_budget']):.2f}"),
    )


def load_venue(data_dir: Path | None = None) -> Venue:
    folder = data_dir or DATA_DIR
    rules = load_rules(folder / "rules.json")
    rates = {row["staff_id"]: _cents(row["hourly_rate"]) for row in _read_csv(folder / "pay_rates.csv")}
    windows: dict[str, dict[str, tuple[int, int]]] = {}
    for row in _read_csv(folder / "availability.csv"):
        if row["day"] not in DAYS:
            raise ValueError(f"Unknown day in availability.csv: {row['day']}")
        start, end = int(row["from_hour"]), int(row["until_hour"])
        if end <= start:
            raise ValueError(f"Bad window for {row['staff_id']} on {row['day']}")
        windows.setdefault(row["staff_id"], {})[row["day"]] = (start, end)

    staff: list[Staff] = []
    seen: set[str] = set()
    for row in _read_csv(folder / "staff.csv"):
        sid = row["staff_id"]
        if sid in seen:
            raise ValueError(f"Duplicate staff id {sid}")
        seen.add(sid)
        if sid not in rates:
            raise ValueError(f"No pay rate for {sid}")
        if row["area"] not in AREAS:
            raise ValueError(f"Bad area for {sid}: {row['area']}")
        staff.append(
            Staff(
                id=sid,
                name=row["name"],
                area=row["area"],
                can_open=row["can_open"].strip().lower() == "yes",
                can_close=row["can_close"].strip().lower() == "yes",
                max_minutes=_hours(row["max_hours"]),
                rate_cents=rates[sid],
                windows=windows.get(sid, {}),
            )
        )

    traffic: dict[tuple[str, int], int] = {}
    for row in _read_csv(folder / "foot_traffic.csv"):
        if row["day"] not in DAYS:
            raise ValueError(f"Unknown day in foot_traffic.csv: {row['day']}")
        key = (row["day"], int(row["hour"]))
        if key in traffic:
            raise ValueError(f"Duplicate traffic row {key}")
        traffic[key] = int(row["entries"])

    hours = sorted({hour for _, hour in traffic})
    for day in DAYS:
        for hour in range(rules.open_hour, rules.close_hour + 1):
            if (day, hour) not in traffic:
                raise ValueError(f"Missing traffic for {day} {hour}:00")
    return Venue(rules=rules, staff=staff, traffic=traffic, hours=hours)
