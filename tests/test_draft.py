"""Draft, repair, and trim on small venues and on the sample week."""

from roster_builder.data import DAYS, Shift, Staff, load_venue
from roster_builder.draft import draft_shifts, repair_shifts, trim_shifts
from roster_builder.rules import compliance_violations, coverage_gaps, roster_cost_cents
from tests.test_rules import _person, _venue


def test_draft_sample_week_misses_breaks_or_minimums_and_repair_clears_them():
    venue = load_venue()
    drafted, notes = draft_shifts(venue)
    assert notes
    draft_codes = {item["code"] for item in compliance_violations(venue, drafted)}
    assert draft_codes & {"meal_break", "min_shift"}
    repaired, actions = repair_shifts(venue, drafted)
    assert actions != ["no change"]
    assert compliance_violations(venue, repaired) == []
    assert coverage_gaps(venue, repaired) == []


def test_repair_bridges_a_same_day_split_and_adds_the_break():
    maya = _person(max_minutes=40 * 60)
    venue = _venue([maya], hours=range(11, 22), days=["Monday"], traffic_entries=10)
    splits = [Shift("maya", "Monday", 11, 14), Shift("maya", "Monday", 17, 21)]
    assert "rest_gap" in {item["code"] for item in compliance_violations(venue, splits)}
    repaired, _actions = repair_shifts(venue, splits)
    monday = [shift for shift in repaired if shift.day == "Monday" and shift.staff_id == "maya"]
    assert len(monday) == 1
    assert monday[0].break_minutes == 30
    assert "rest_gap" not in {item["code"] for item in compliance_violations(venue, repaired)}


def test_trim_removes_a_surplus_edge_and_stops_before_the_closer():
    maya = _person(id="maya", rate_cents=3400)
    priya = _person(
        id="priya",
        name="Priya Shah",
        can_open=False,
        can_close=False,
        rate_cents=2600,
        max_minutes=30 * 60,
    )
    venue = _venue([maya, priya], traffic_entries=10)  # front need 1, kitchen 0
    # Both work 11-16. Hour 11 and 15 are surplus edges. Maya is the only closer
    # if we ever cut her off hour 21, but 21 is not in this shift.
    shifts = [
        Shift("maya", "Monday", 11, 16),
        Shift("priya", "Monday", 11, 16),
    ]
    tight = _venue(
        [maya, priya],
        hours=range(11, 17),
        days=["Monday"],
        traffic_entries=10,
        weekly_labour_budget_cents=1,
    )
    trimmed, actions = trim_shifts(tight, shifts)
    assert "removed" in actions[0]
    assert roster_cost_cents(tight, trimmed) < roster_cost_cents(tight, shifts)
    # Monday 11:00 still has an opener, and nobody was left on a 2h shift.
    codes = {item["code"] for item in compliance_violations(tight, trimmed)}
    assert "min_shift" not in codes
    assert "opener" not in codes


def test_two_drafts_match():
    venue = load_venue()
    first, _ = draft_shifts(venue)
    second, _ = draft_shifts(venue)
    key = lambda shifts: [(s.staff_id, s.day, s.start, s.end, s.break_minutes) for s in shifts]
    assert key(first) == key(second)


def test_handoff_uses_front_closer_not_the_kitchen_lead():
    venue = load_venue()
    drafted, _notes = draft_shifts(venue)
    repaired, _actions = repair_shifts(venue, drafted)
    by_id = venue.staff_by_id()
    for day in DAYS:
        closers = [
            by_id[shift.staff_id]
            for shift in repaired
            if shift.day == day
            and shift.start <= 21 < shift.end
            and by_id[shift.staff_id].can_close
            and by_id[shift.staff_id].area == "front"
        ]
        assert closers, day
