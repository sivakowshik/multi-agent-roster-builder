"""Greedy coverage draft, then repair and trim. Deterministic, no model calls.

The draft covers each hour and stops. It does not insert meal breaks.
repair_compliance is a separate function so the checker is not grading
the drafter's own homework.
"""

from __future__ import annotations

from roster_builder.data import DAYS, AREAS, Shift, Staff, Venue
from roster_builder.rules import headcount

HourMap = dict[str, dict[str, set[int]]]


def blocks_of(hours: set[int]) -> list[tuple[int, int]]:
    if not hours:
        return []
    ordered = sorted(hours)
    out: list[tuple[int, int]] = []
    start = prev = ordered[0]
    for hour in ordered[1:]:
        if hour == prev + 1:
            prev = hour
        else:
            out.append((start, prev + 1))
            start = prev = hour
    out.append((start, prev + 1))
    return out


def break_minutes_for(span_minutes: int, venue: Venue) -> int:
    rules = venue.rules
    if span_minutes > rules.meal_break_after_minutes:
        return rules.meal_break_minutes
    return 0


def empty_assigned(venue: Venue) -> HourMap:
    return {person.id: {day: set() for day in DAYS} for person in venue.staff}


def assigned_from_shifts(venue: Venue, shifts: list[Shift]) -> HourMap:
    assigned = empty_assigned(venue)
    known = set(assigned)
    for shift in shifts:
        if shift.staff_id not in known:
            continue
        for hour in range(shift.start, shift.end):
            assigned[shift.staff_id][shift.day].add(hour)
    return assigned


def paid_minutes(hourmap: dict[str, set[int]], venue: Venue, with_breaks: bool) -> int:
    total = 0
    for day in DAYS:
        for start, end in blocks_of(hourmap.get(day, set())):
            span = (end - start) * 60
            unpaid = break_minutes_for(span, venue) if with_breaks else 0
            total += span - unpaid
    return total


def _start_minute(day: str, hour: int) -> int:
    return DAYS.index(day) * 24 * 60 + hour * 60


def rest_ok(hourmap: dict[str, set[int]], venue: Venue) -> bool:
    blocks: list[tuple[str, int, int]] = []
    for day in DAYS:
        for start, end in blocks_of(hourmap.get(day, set())):
            blocks.append((day, start, end))
    if len(blocks) < 2:
        return True
    ordered = sorted(blocks, key=lambda block: _start_minute(block[0], block[1]))
    gaps = []
    for earlier, later in zip(ordered, ordered[1:]):
        gaps.append(_start_minute(later[0], later[1]) - _start_minute(earlier[0], earlier[2]))
    wrap = (_start_minute(ordered[0][0], ordered[0][1]) + 7 * 24 * 60) - _start_minute(ordered[-1][0], ordered[-1][2])
    gaps.append(wrap)
    return all(gap >= venue.rules.min_rest_minutes for gap in gaps)


def _window_ok(person: Staff, day: str, hour: int, venue: Venue) -> bool:
    window = person.windows.get(day)
    if window is None or hour not in venue.hours:
        return False
    return window[0] <= hour < window[1]


def can_place(person: Staff, day: str, hours: list[int], assigned: HourMap, venue: Venue) -> bool:
    if not hours:
        return True
    current = assigned[person.id]
    for hour in hours:
        if hour in current[day] or not _window_ok(person, day, hour, venue):
            return False
    trial = {key: set(value) for key, value in current.items()}
    for hour in hours:
        trial[day].add(hour)
    if paid_minutes(trial, venue, with_breaks=False) > venue.cap_minutes(person):
        return False
    return rest_ok(trial, venue)


def _count(assigned: HourMap, venue: Venue, day: str, hour: int, area: str) -> int:
    total = 0
    for person in venue.staff:
        if person.area == area and hour in assigned[person.id][day]:
            total += 1
    return total


def _need(venue: Venue, day: str, hour: int, area: str) -> int:
    if (day, hour) not in venue.traffic:
        return 0
    return headcount(venue.traffic[(day, hour)], area, venue)


def _skill_missing(person: Staff, need_open: bool, need_close: bool) -> int:
    if need_close and not person.can_close:
        return 1
    if need_open and not person.can_open:
        return 1
    return 0


def ranked_staff(
    venue: Venue,
    assigned: HourMap,
    day: str,
    hour: int,
    area: str,
    respect_rest: bool,
    predicate=None,
) -> list[Staff]:
    present = [
        person
        for person in venue.staff
        if person.area == area and hour in assigned[person.id][day]
    ]
    need_close = area == "front" and hour == venue.rules.close_hour and not any(person.can_close for person in present)
    need_open = area == "front" and hour == venue.rules.open_hour and not any(person.can_open for person in present)
    ranked: list[tuple] = []
    for person in venue.staff:
        if person.area != area or not _window_ok(person, day, hour, venue):
            continue
        if predicate is not None and not predicate(person):
            continue
        if hour in assigned[person.id][day]:
            continue
        trial = {key: set(value) for key, value in assigned[person.id].items()}
        trial[day].add(hour)
        if paid_minutes(trial, venue, with_breaks=False) > venue.cap_minutes(person):
            continue
        if respect_rest and not rest_ok(trial, venue):
            continue
        adjacent = (hour - 1 in assigned[person.id][day]) or (hour + 1 in assigned[person.id][day])
        ranked.append(
            (
                _skill_missing(person, need_open, need_close),
                0 if adjacent else 1,
                person.rate_cents,
                person.id,
                person,
            )
        )
    ranked.sort()
    return [item[-1] for item in ranked]


def try_assign(person: Staff, day: str, hours: list[int], assigned: HourMap, venue: Venue) -> bool:
    """Place these hours and grow the block to the minimum shift, or leave it untouched."""
    snapshot = set(assigned[person.id][day])
    fresh = [hour for hour in hours if hour not in snapshot]
    if fresh and not can_place(person, day, fresh, assigned, venue):
        return False
    assigned[person.id][day].update(fresh)
    target = (fresh or hours)[-1]
    minimum = venue.rules.min_shift_minutes // 60
    for _ in range(16):
        block = next(
            (item for item in blocks_of(assigned[person.id][day]) if item[0] <= target < item[1]),
            None,
        )
        if block is None or block[1] - block[0] >= minimum:
            return True
        start, end = block
        placed = False
        for candidate in (end, start - 1):
            if can_place(person, day, [candidate], assigned, venue):
                assigned[person.id][day].add(candidate)
                placed = True
                break
        if not placed:
            assigned[person.id][day].clear()
            assigned[person.id][day].update(snapshot)
            return False
    assigned[person.id][day].clear()
    assigned[person.id][day].update(snapshot)
    return False


def assign_hour(venue: Venue, assigned: HourMap, day: str, hour: int, area: str) -> bool:
    for person in ranked_staff(venue, assigned, day, hour, area, respect_rest=True):
        if try_assign(person, day, [hour], assigned, venue):
            return True
    for person in ranked_staff(venue, assigned, day, hour, area, respect_rest=False):
        extra = _bridge_hours(assigned[person.id][day], hour)
        if extra and try_assign(person, day, extra + [hour], assigned, venue):
            return True
    return False


def _skill_present(venue: Venue, assigned: HourMap, day: str, hour: int, predicate) -> bool:
    return any(
        predicate(person) and hour in assigned[person.id][day]
        for person in venue.staff
        if person.area == "front"
    )


def force_skill(venue: Venue, assigned: HourMap, day: str, hour: int, predicate) -> bool:
    if _skill_present(venue, assigned, day, hour, predicate):
        return True
    options = [
        person
        for person in venue.staff
        if person.area == "front" and predicate(person) and _window_ok(person, day, hour, venue)
    ]
    options.sort(key=lambda person: (0 if assigned[person.id][day] else 1, person.rate_cents, person.id))
    for person in options:
        extra = _bridge_hours(assigned[person.id][day], hour)
        if try_assign(person, day, extra + [hour], assigned, venue):
            return True
    return False


def cover_hour(venue: Venue, assigned: HourMap, day: str, hour: int) -> int:
    filled = 0
    for area in AREAS:
        while _count(assigned, venue, day, hour, area) < _need(venue, day, hour, area):
            if not assign_hour(venue, assigned, day, hour, area):
                break
            filled += 1
    if hour == venue.rules.open_hour:
        force_skill(venue, assigned, day, hour, lambda person: person.can_open)
    if hour == venue.rules.close_hour:
        force_skill(venue, assigned, day, hour, lambda person: person.can_close)
    return filled


def _bridge_hours(existing: set[int], hour: int) -> list[int]:
    if not existing or hour in existing:
        return []
    earlier = [item for item in existing if item < hour]
    later = [item for item in existing if item > hour]
    if earlier and (not later or hour - max(earlier) <= (min(later) - hour if later else 99)):
        return list(range(max(earlier) + 1, hour))
    if later:
        return list(range(hour + 1, min(later)))
    return []


def fill_gaps(venue: Venue, assigned: HourMap) -> int:
    filled = 0
    for day in DAYS:
        for hour in venue.hours:
            filled += cover_hour(venue, assigned, day, hour)
    return filled


def shifts_from_assigned(venue: Venue, assigned: HourMap, with_breaks: bool) -> list[Shift]:
    shifts: list[Shift] = []
    for person in venue.staff:
        for day in DAYS:
            for start, end in blocks_of(assigned[person.id][day]):
                span = (end - start) * 60
                unpaid = break_minutes_for(span, venue) if with_breaks else 0
                shifts.append(Shift(person.id, day, start, end, unpaid))
    return shifts


def draft_shifts(venue: Venue) -> tuple[list[Shift], list[str]]:
    assigned = empty_assigned(venue)
    notes: list[str] = []
    for day in DAYS:
        for hour in venue.hours:
            cover_hour(venue, assigned, day, hour)
            for area in AREAS:
                short = _need(venue, day, hour, area) - _count(assigned, venue, day, hour, area)
                if short > 0:
                    notes.append(f"uncovered {day} {hour:02d}:00 {area}, short {short}")
    if not notes:
        notes.append("all demanded hours covered")
    return shifts_from_assigned(venue, assigned, with_breaks=False), notes


def bridge_rest_gaps(venue: Venue, assigned: HourMap) -> int:
    """Fill a same-day hole when the two blocks are closer than the rest rule."""
    bridged = 0
    for person in venue.staff:
        for day in DAYS:
            progressed = True
            while progressed:
                progressed = False
                blocks = blocks_of(assigned[person.id][day])
                for (_left_start, left_end), (right_start, _right_end) in zip(blocks, blocks[1:]):
                    if (right_start - left_end) * 60 >= venue.rules.min_rest_minutes:
                        continue
                    gap = list(range(left_end, right_start))
                    if gap and can_place(person, day, gap, assigned, venue):
                        assigned[person.id][day].update(gap)
                        bridged += 1
                        progressed = True
                        break
    return bridged


def _snapshot(assigned: HourMap) -> tuple:
    rows = []
    for staff_id in sorted(assigned):
        for day in DAYS:
            for hour in sorted(assigned[staff_id][day]):
                rows.append((staff_id, day, hour))
    return tuple(rows)


def _only_skilled(venue: Venue, assigned: HourMap, person: Staff, day: str, hour: int) -> bool:
    if person.area != "front":
        return False
    others = [
        other
        for other in venue.staff
        if other.id != person.id and other.area == "front" and hour in assigned[other.id][day]
    ]
    if hour == venue.rules.open_hour and person.can_open and not any(other.can_open for other in others):
        return True
    if hour == venue.rules.close_hour and person.can_close and not any(other.can_close for other in others):
        return True
    return False


def _extend_block(person: Staff, day: str, assigned: HourMap, venue: Venue) -> bool:
    changed = False
    min_hours = venue.rules.min_shift_minutes // 60
    grew = True
    while grew:
        grew = False
        for start, end in blocks_of(assigned[person.id][day]):
            if end - start >= min_hours:
                continue
            for hour in (end, start - 1):
                if can_place(person, day, [hour], assigned, venue):
                    assigned[person.id][day].add(hour)
                    changed = True
                    grew = True
                    break
            if grew:
                break
    return changed


def _drop_still_short(person: Staff, day: str, assigned: HourMap, venue: Venue) -> int:
    min_hours = venue.rules.min_shift_minutes // 60
    dropped = 0
    for start, end in blocks_of(set(assigned[person.id][day])):
        if end - start >= min_hours:
            continue
        for hour in range(start, end):
            assigned[person.id][day].discard(hour)
            dropped += 1
    return dropped


def _shave(venue: Venue, assigned: HourMap) -> int:
    removed = 0
    min_hours = venue.rules.min_shift_minutes // 60
    for person in venue.staff:
        guard = 0
        while paid_minutes(assigned[person.id], venue, with_breaks=False) > venue.cap_minutes(person):
            guard += 1
            if guard > 40:
                break
            cut = _best_hour_to_drop(venue, assigned, person, min_hours)
            if cut is None:
                break
            day, hour = cut
            assigned[person.id][day].remove(hour)
            removed += 1
    return removed


def _best_hour_to_drop(venue: Venue, assigned: HourMap, person: Staff, min_hours: int):
    options = []
    for day in DAYS:
        for start, end in blocks_of(assigned[person.id][day]):
            if end - start <= min_hours:
                continue
            for hour in (start, end - 1):
                if _only_skilled(venue, assigned, person, day, hour):
                    continue
                surplus = _count(assigned, venue, day, hour, person.area) - _need(venue, day, hour, person.area)
                traffic = venue.traffic.get((day, hour), 0)
                options.append((0 if surplus > 0 else 1, traffic, day, hour))
    if not options:
        return None
    options.sort(key=lambda item: (item[0], item[1], DAYS.index(item[2]), item[3]))
    return options[0][2], options[0][3]


def repair_shifts(venue: Venue, shifts: list[Shift]) -> tuple[list[Shift], list[str]]:
    assigned = assigned_from_shifts(venue, shifts)
    for _ in range(4):
        before = _snapshot(assigned)
        bridge_rest_gaps(venue, assigned)
        fill_gaps(venue, assigned)
        for person in venue.staff:
            for day in DAYS:
                _extend_block(person, day, assigned, venue)
        for person in venue.staff:
            for day in DAYS:
                _drop_still_short(person, day, assigned, venue)
        fill_gaps(venue, assigned)
        _shave(venue, assigned)
        if _snapshot(assigned) == before:
            break
    after = shifts_from_assigned(venue, assigned, with_breaks=True)
    return after, _repair_actions(venue, shifts, after)


def _repair_actions(venue: Venue, before: list[Shift], after: list[Shift]) -> list[str]:
    actions = []
    breaks = sum(1 for shift in after if shift.break_minutes)
    if breaks:
        actions.append(
            f"set a {venue.rules.meal_break_minutes}m unpaid meal break on {breaks} shifts over "
            f"{venue.rules.meal_break_after_minutes // 60}h"
        )
    before_key = {(shift.staff_id, shift.day, shift.start, shift.end) for shift in before}
    after_key = {(shift.staff_id, shift.day, shift.start, shift.end) for shift in after}
    if before_key != after_key:
        actions.append("adjusted shift times for the minimum length, the rest gap, and open/close cover")
    if not actions:
        actions.append("no change")
    return actions


def _surplus(venue: Venue, assigned: HourMap, person: Staff, day: str, hour: int) -> bool:
    return _count(assigned, venue, day, hour, person.area) > _need(venue, day, hour, person.area)


def trim_shifts(venue: Venue, shifts: list[Shift]) -> tuple[list[Shift], list[str]]:
    from roster_builder.rules import roster_cost_cents

    assigned = assigned_from_shifts(venue, shifts)
    budget = venue.rules.weekly_labour_budget_cents
    min_hours = venue.rules.min_shift_minutes // 60
    removed: list[str] = []
    guard = 0
    while True:
        current = shifts_from_assigned(venue, assigned, with_breaks=True)
        if roster_cost_cents(venue, current) <= budget:
            break
        guard += 1
        if guard > 200:
            break
        cut = _best_trim(venue, assigned, min_hours)
        if cut is None:
            break
        person, day, hour = cut
        assigned[person.id][day].remove(hour)
        removed.append(f"{person.name} {day} {hour:02d}:00")
    actions = []
    if removed:
        actions.append(f"removed {len(removed)} surplus hours: " + ", ".join(removed[:8]) + ("..." if len(removed) > 8 else ""))
    else:
        actions.append("no surplus hour could be removed without breaking a sample rule or leaving demand uncovered")
    return shifts_from_assigned(venue, assigned, with_breaks=True), actions


def _best_trim(venue: Venue, assigned: HourMap, min_hours: int):
    options = []
    for person in venue.staff:
        for day in DAYS:
            for start, end in blocks_of(assigned[person.id][day]):
                if end - start <= min_hours:
                    continue
                for hour in (start, end - 1):
                    if not _surplus(venue, assigned, person, day, hour):
                        continue
                    if _only_skilled(venue, assigned, person, day, hour):
                        continue
                    trial = {key: set(value) for key, value in assigned[person.id].items()}
                    trial[day].remove(hour)
                    if not rest_ok(trial, venue):
                        continue
                    options.append((person.rate_cents, venue.traffic.get((day, hour), 0), person.id, day, hour, person))
    if not options:
        return None
    options.sort(key=lambda item: (-item[0], item[1], item[2], DAYS.index(item[3]), item[4]))
    best = options[0]
    return best[5], best[3], best[4]
