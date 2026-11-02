"""Rule checks and cost maths. No network."""

from roster_builder.data import DAYS, Shift, Staff, Venue, load_venue
from roster_builder.rules import (
    compliance_violations,
    cost_report,
    headcount,
    roster_cost_cents,
)


def _rules():
    return load_venue().rules


def _person(**overrides) -> Staff:
    base = dict(
        id="maya",
        name="Maya Patel",
        area="front",
        can_open=True,
        can_close=True,
        max_minutes=38 * 60,
        rate_cents=3400,
        windows={day: (8, 23) for day in DAYS},
    )
    base.update(overrides)
    return Staff(**base)


def _venue(staff, hours=(11, 21), traffic_entries=20, days=None, **rule_overrides) -> Venue:
    loaded = _rules()
    values = loaded.__dict__.copy()
    values.update(rule_overrides)
    rules = loaded.__class__(**values)
    hours = list(hours)
    days = list(DAYS if days is None else days)
    traffic = {(day, hour): traffic_entries for day in days for hour in hours}
    return Venue(rules=rules, staff=staff, traffic=traffic, hours=hours)


def _codes(venue, shifts):
    return [item["code"] for item in compliance_violations(venue, shifts)]


def test_headcount_front_and_kitchen():
    venue = load_venue()
    assert headcount(0, "front", venue) == 1
    assert headcount(28, "front", venue) == 1
    assert headcount(29, "front", venue) == 2
    assert headcount(56, "front", venue) == 2
    assert headcount(57, "front", venue) == 3
    assert headcount(200, "front", venue) == 4
    assert headcount(17, "kitchen", venue) == 0
    assert headcount(18, "kitchen", venue) == 1
    assert headcount(49, "kitchen", venue) == 1
    assert headcount(50, "kitchen", venue) == 2


def test_meal_break_and_min_shift():
    maya = _person()
    venue = _venue([maya])
    short = Shift("maya", "Monday", 11, 12)
    long = Shift("maya", "Tuesday", 11, 18)
    codes = _codes(venue, [short, long])
    assert "min_shift" in codes
    assert "meal_break" in codes
    fixed = Shift("maya", "Tuesday", 11, 18, break_minutes=30)
    assert "meal_break" not in _codes(venue, [Shift("maya", "Monday", 11, 14), fixed])


def test_rest_gap_wraps_the_week():
    maya = _person()
    venue = _venue([maya], hours=list(range(6, 23)))
    shifts = [
        Shift("maya", "Sunday", 18, 23),
        Shift("maya", "Monday", 6, 10),
    ]
    assert "rest_gap" in _codes(venue, shifts)
    # 23:00 Sunday to 11:00 Monday is 12h, which clears a 10h gap.
    ok = [Shift("maya", "Sunday", 18, 22), Shift("maya", "Monday", 11, 15)]
    assert "rest_gap" not in _codes(venue, ok)


def test_overlap_and_max_hours_and_availability():
    maya = _person(max_minutes=10 * 60, windows={"Monday": (11, 15)})
    venue = _venue([maya])
    overlap = [Shift("maya", "Monday", 11, 14), Shift("maya", "Monday", 13, 16)]
    assert "overlap" in _codes(venue, overlap)
    over = [Shift("maya", "Monday", 11, 14), Shift("maya", "Tuesday", 11, 18, break_minutes=0)]
    # Tuesday is outside the window, and paid hours are 3 + 7 = 10 exactly, so max is not over.
    assert "availability" in _codes(venue, over)
    too_long = [Shift("maya", "Monday", 11, 14), Shift("maya", "Tuesday", 11, 20)]
    venue_open = _venue([maya], hours=list(range(11, 23)))
    # window only Monday 11-15, Tuesday missing entirely
    assert "availability" in _codes(venue_open, too_long)
    capped = _person(max_minutes=5 * 60)
    venue_cap = _venue([capped])
    assert "max_hours" in _codes(venue_cap, [Shift("maya", "Monday", 11, 18, break_minutes=30)])


def test_kitchen_closer_does_not_count():
    cook = _person(id="hannah", name="Hannah Okonkwo", area="kitchen", can_open=False, can_close=True, rate_cents=3200)
    venue = _venue([cook])
    shift = Shift("hannah", "Monday", 11, 22, break_minutes=30)
    codes = _codes(venue, [shift])
    assert "closer" in codes
    assert "opener" in codes


def test_opener_and_closer_pass_when_front_trained_staff_cover():
    maya = _person()
    venue = _venue([maya], days=["Monday"])
    shift = Shift("maya", "Monday", 11, 22, break_minutes=30)
    assert _codes(venue, [shift]) == []


def test_cost_is_paid_hours_times_rate_in_cents():
    person = _person(rate_cents=2750, max_minutes=40 * 60)
    venue = _venue([person])
    shift = Shift("maya", "Monday", 12, 18, break_minutes=30)  # 5.5h paid? span 6h, break 30, paid 5.5h
    # 330 minutes * 2750 // 60 = 15125 cents = $151.25
    assert shift.paid_minutes() == 330
    assert roster_cost_cents(venue, [shift]) == 330 * 2750 // 60
    report = cost_report(venue, [shift])
    assert report["labour_cost"] == "$151.25"
    assert report["passed"] is True


def test_sample_files_are_complete_and_labelled():
    from pathlib import Path

    venue = load_venue()
    assert venue.rules.venue == "Helio Grill"
    assert "not legal advice" in venue.rules.disclaimer.lower()
    assert len(venue.traffic) == 7 * 11
    assert {person.area for person in venue.staff} == {"front", "kitchen"}
    text = Path("data/FICTIONAL.txt").read_text().lower()
    assert "fictional" in text
    assert "does not read video" in text
