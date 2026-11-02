"""Staffing counts, sample rule checks, and labour cost. No model calls."""

from __future__ import annotations

from roster_builder.data import DAYS, AREAS, Shift, Staff, Venue


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100:,}.{cents % 100:02d}"


def hours_label(minutes: int) -> str:
    if minutes % 60 == 0:
        return str(minutes // 60)
    if minutes % 30 == 0:
        return f"{minutes / 60:.1f}"
    return f"{minutes / 60:.2f}"


def clock(hour: int) -> str:
    return f"{hour:02d}:00"


def headcount(entries: int, area: str, venue: Venue) -> int:
    rules = venue.rules
    if area == "front":
        people = max(1, (entries + rules.front_entries_per_person - 1) // rules.front_entries_per_person)
        return min(rules.max_front, people)
    if entries < rules.kitchen_quiet_below:
        return 0
    if entries < rules.kitchen_second_from:
        return 1
    return 2


def staffing_rows(venue: Venue) -> list[dict]:
    rows = []
    for day in DAYS:
        for hour in venue.hours:
            entries = venue.traffic[(day, hour)]
            rows.append(
                {
                    "day": day,
                    "hour": clock(hour),
                    "hour_index": hour,
                    "entries": entries,
                    "front": headcount(entries, "front", venue),
                    "kitchen": headcount(entries, "kitchen", venue),
                }
            )
    return rows


def busiest_by_day(rows: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for row in rows:
        current = best.get(row["day"])
        if current is None or row["entries"] > current["entries"]:
            best[row["day"]] = row
    return [best[day] for day in DAYS if day in best]


def _covers(shift: Shift, hour: int) -> bool:
    return shift.start <= hour < shift.end


def _week_minutes(day: str, hour: int) -> int:
    return DAYS.index(day) * 24 * 60 + hour * 60


def rest_gap_minutes(earlier: Shift, later: Shift, wrap: bool = False) -> int:
    start = _week_minutes(later.day, later.start)
    end = _week_minutes(earlier.day, earlier.end)
    if wrap:
        start += 7 * 24 * 60
    return start - end


def shift_cost_cents(shift: Shift, person: Staff) -> int:
    return shift.paid_minutes() * person.rate_cents // 60


def roster_cost_cents(venue: Venue, shifts: list[Shift]) -> int:
    by_id = venue.staff_by_id()
    return sum(shift_cost_cents(shift, by_id[shift.staff_id]) for shift in shifts)


def coverage_gaps(venue: Venue, shifts: list[Shift]) -> list[dict]:
    by_id = venue.staff_by_id()
    gaps = []
    for row in staffing_rows(venue):
        hour = row["hour_index"]
        for area in AREAS:
            have = sum(
                1
                for shift in shifts
                if shift.day == row["day"]
                and _covers(shift, hour)
                and by_id[shift.staff_id].area == area
            )
            if have < row[area]:
                gaps.append(
                    {
                        "day": row["day"],
                        "hour": row["hour"],
                        "area": area,
                        "need": row[area],
                        "have": have,
                    }
                )
    return gaps


def _people_at(venue: Venue, shifts: list[Shift], day: str, hour: int, area: str) -> list[Staff]:
    by_id = venue.staff_by_id()
    found = []
    for shift in shifts:
        if shift.day == day and _covers(shift, hour):
            person = by_id[shift.staff_id]
            if person.area == area:
                found.append(person)
    return found


def compliance_violations(venue: Venue, shifts: list[Shift]) -> list[dict]:
    rules = venue.rules
    by_id = venue.staff_by_id()
    found: list[dict] = []

    def add(code: str, message: str) -> None:
        found.append({"code": code, "message": message})

    for shift in shifts:
        person = by_id.get(shift.staff_id)
        label = f"{shift.day} {clock(shift.start)}-{clock(shift.end)}"
        if person is None:
            add("unknown_staff", f"Unknown staff id {shift.staff_id} on {label}.")
            continue
        who = f"{person.name}, {label}"
        if shift.end <= shift.start:
            add("bad_shift", f"{who} has a non-positive length.")
            continue
        if shift.break_minutes < 0 or shift.break_minutes >= shift.span_minutes():
            add("bad_break", f"{who} has a break of {shift.break_minutes}m on a {hours_label(shift.span_minutes())}h shift.")
        window = person.windows.get(shift.day)
        if window is None:
            add("availability", f"{person.name} is not available on {shift.day}.")
        elif shift.start < window[0] or shift.end > window[1]:
            add(
                "availability",
                f"{who} sits outside availability ({clock(window[0])}-{clock(window[1])}).",
            )
        if shift.span_minutes() < rules.min_shift_minutes:
            add(
                "min_shift",
                f"{who} is {hours_label(shift.span_minutes())}h. Sample rule: minimum shift is {hours_label(rules.min_shift_minutes)}h.",
            )
        if shift.span_minutes() > rules.meal_break_after_minutes and shift.break_minutes < rules.meal_break_minutes:
            add(
                "meal_break",
                f"{who} is {hours_label(shift.span_minutes())}h with a {shift.break_minutes}m break. "
                f"Sample rule: a shift longer than {hours_label(rules.meal_break_after_minutes)}h needs a {rules.meal_break_minutes}m meal break.",
            )

    for person in venue.staff:
        theirs = sorted(
            (shift for shift in shifts if shift.staff_id == person.id and shift.end > shift.start),
            key=lambda shift: (_week_minutes(shift.day, shift.start), shift.end),
        )
        paid = sum(shift.paid_minutes() for shift in theirs)
        cap = venue.cap_minutes(person)
        if paid > cap:
            add(
                "max_hours",
                f"{person.name} is rostered {hours_label(paid)}h. Sample rule: maximum is {hours_label(cap)}h.",
            )
        if len(theirs) < 2:
            continue
        pairs = [(theirs[i], theirs[i + 1], False) for i in range(len(theirs) - 1)]
        pairs.append((theirs[-1], theirs[0], True))
        for earlier, later, wrap in pairs:
            if not wrap and earlier.day == later.day and earlier.end > later.start:
                add("overlap", f"Two shifts overlap for {person.name} on {earlier.day}.")
                continue
            gap = rest_gap_minutes(earlier, later, wrap=wrap)
            if gap < rules.min_rest_minutes:
                add(
                    "rest_gap",
                    f"{person.name}, {earlier.day} {clock(earlier.end)} to {later.day} {clock(later.start)} "
                    f"is a {hours_label(gap)}h gap. Sample rule: minimum rest between shifts is {hours_label(rules.min_rest_minutes)}h.",
                )

    for day in DAYS:
        if (day, rules.open_hour) in venue.traffic:
            openers = [person for person in _people_at(venue, shifts, day, rules.open_hour, "front") if person.can_open]
            if not openers:
                add("opener", f"{day} {clock(rules.open_hour)} has no open-trained front staff on shift.")
        if (day, rules.close_hour) in venue.traffic:
            closers = [person for person in _people_at(venue, shifts, day, rules.close_hour, "front") if person.can_close]
            if not closers:
                add("closer", f"{day} {clock(rules.close_hour)} has no close-trained front staff on shift.")

    found.sort(key=lambda item: (item["code"], item["message"]))
    return found


def cost_report(venue: Venue, shifts: list[Shift]) -> dict:
    by_id = venue.staff_by_id()
    by_staff = []
    by_day = []
    for person in venue.staff:
        paid = sum(shift.paid_minutes() for shift in shifts if shift.staff_id == person.id)
        if paid == 0:
            continue
        cents = paid * person.rate_cents // 60
        by_staff.append(
            {
                "name": person.name,
                "paid_hours": hours_label(paid),
                "cost": money(cents),
            }
        )
    for day in DAYS:
        day_shifts = [shift for shift in shifts if shift.day == day]
        paid = sum(shift.paid_minutes() for shift in day_shifts)
        cents = sum(shift_cost_cents(shift, by_id[shift.staff_id]) for shift in day_shifts)
        by_day.append({"day": day, "paid_hours": hours_label(paid), "cost": money(cents)})
    total = roster_cost_cents(venue, shifts)
    budget = venue.rules.weekly_labour_budget_cents
    delta = total - budget
    if delta > 0:
        delta_label = f"over by {money(delta)}"
        verdict = "COST_FAIL"
    elif delta < 0:
        delta_label = f"under by {money(-delta)}"
        verdict = "COST_PASS"
    else:
        delta_label = "on budget"
        verdict = "COST_PASS"
    paid_total = sum(shift.paid_minutes() for shift in shifts)
    return {
        "passed": total <= budget,
        "verdict": verdict,
        "paid_hours": hours_label(paid_total),
        "labour_cost": money(total),
        "labour_cost_cents": total,
        "weekly_budget": money(budget),
        "weekly_budget_cents": budget,
        "delta_label": delta_label,
        "by_staff": by_staff,
        "by_day": by_day,
        "note": venue.rules.cost_note,
    }
