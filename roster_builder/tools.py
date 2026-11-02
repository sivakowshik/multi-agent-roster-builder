"""Tools the agents call. Numbers come from rules.py and draft.py, not the model."""

from __future__ import annotations

import json

from roster_builder.data import Venue, load_venue
from roster_builder.draft import draft_shifts, repair_shifts, trim_shifts
from roster_builder.report import format_roster
from roster_builder.rules import (
    busiest_by_day,
    compliance_violations,
    cost_report,
    coverage_gaps,
    hours_label,
    money,
    roster_cost_cents,
    staffing_rows,
)

_venue: Venue | None = None
_shifts: list | None = None


def reset_board(venue: Venue | None = None) -> None:
    global _venue, _shifts
    _venue = venue or load_venue()
    _shifts = []


def board() -> tuple[Venue, list]:
    if _venue is None or _shifts is None:
        reset_board()
    assert _venue is not None and _shifts is not None
    return _venue, _shifts


def _dump(payload: dict) -> str:
    return json.dumps(payload, indent=2)


def _shift_summary(venue: Venue, shifts: list) -> dict:
    paid = sum(shift.paid_minutes() for shift in shifts)
    cents = roster_cost_cents(venue, shifts)
    gaps = coverage_gaps(venue, shifts)
    return {
        "shift_count": len(shifts),
        "paid_hours": hours_label(paid),
        "cost": money(cents),
        "cost_cents": cents,
        "coverage_gaps": gaps,
        "roster": format_roster(venue, shifts),
    }


def staffing_needs() -> str:
    """Hourly foot traffic and the front/kitchen headcount that traffic implies. Read-only."""
    venue, _ = board()
    rows = staffing_rows(venue)
    return _dump(
        {
            "venue": venue.rules.venue,
            "note": (
                "Fictional hourly entry counts, in the shape a CCTV people-counter would export. "
                "This tool does not read video."
            ),
            "rule": (
                f"Front: 1 person per {venue.rules.front_entries_per_person} entries, minimum 1 while open, "
                f"capped at {venue.rules.max_front}. "
                f"Kitchen: 0 below {venue.rules.kitchen_quiet_below} entries, "
                f"1 until {venue.rules.kitchen_second_from}, then 2."
            ),
            "busiest": busiest_by_day(rows),
            "hours": rows,
        }
    )


def draft_roster() -> str:
    """Cover each demanded hour with available staff. Does not insert meal breaks."""
    venue, shifts = board()
    drafted, notes = draft_shifts(venue)
    shifts.clear()
    shifts.extend(drafted)
    payload = _shift_summary(venue, shifts)
    payload["notes"] = notes
    payload["breaks_inserted"] = False
    return _dump(payload)


def check_compliance() -> str:
    """Check the current roster against the sample house rules. Not legal advice."""
    venue, shifts = board()
    violations = compliance_violations(venue, shifts)
    passed = not violations
    return _dump(
        {
            "passed": passed,
            "verdict": "COMPLIANCE_PASS" if passed else "COMPLIANCE_FAIL",
            "violation_count": len(violations),
            "violations": violations,
            "coverage_gaps": coverage_gaps(venue, shifts),
            "disclaimer": venue.rules.disclaimer,
        }
    )


def check_labour_cost() -> str:
    """Compare base-rate labour cost of the current roster with the weekly budget."""
    venue, shifts = board()
    return _dump(cost_report(venue, shifts))


def repair_compliance() -> str:
    """Extend short shifts, place a trained opener and closer, and insert meal breaks."""
    venue, shifts = board()
    repaired, actions = repair_shifts(venue, list(shifts))
    shifts.clear()
    shifts.extend(repaired)
    payload = _shift_summary(venue, shifts)
    payload["actions"] = actions
    payload["changed"] = actions != ["no change"]
    return _dump(payload)


def trim_to_budget() -> str:
    """Drop surplus edge hours, dearest first, without breaking the sample rules or demand."""
    venue, shifts = board()
    trimmed, actions = trim_shifts(venue, list(shifts))
    before = roster_cost_cents(venue, shifts)
    shifts.clear()
    shifts.extend(trimmed)
    after = roster_cost_cents(venue, shifts)
    payload = _shift_summary(venue, shifts)
    payload["actions"] = actions
    payload["changed"] = after != before
    payload["saved"] = money(before - after)
    return _dump(payload)
