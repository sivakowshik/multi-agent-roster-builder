"""Plain-text roster table. Same formatter for the demo and run.py."""

from __future__ import annotations

from roster_builder.data import DAYS, Shift, Venue
from roster_builder.rules import clock, hours_label, money, roster_cost_cents, shift_cost_cents


def format_roster(venue: Venue, shifts: list[Shift]) -> str:
    by_id = venue.staff_by_id()
    ordered = sorted(shifts, key=lambda shift: (DAYS.index(shift.day), shift.start, shift.staff_id))
    header = f"| Day | Staff | Area | Start | End | Break | Paid | Cost |"
    rule = "| --- | --- | --- | --- | --- | --- | --- | --- |"
    lines = [header, rule]
    for shift in ordered:
        person = by_id[shift.staff_id]
        lines.append(
            "| {day} | {name} | {area} | {start} | {end} | {brk}m | {paid}h | {cost} |".format(
                day=shift.day,
                name=person.name,
                area=person.area,
                start=clock(shift.start),
                end=clock(shift.end),
                brk=shift.break_minutes,
                paid=hours_label(shift.paid_minutes()),
                cost=money(shift_cost_cents(shift, person)),
            )
        )
    total_paid = sum(shift.paid_minutes() for shift in shifts)
    total = roster_cost_cents(venue, shifts)
    budget = venue.rules.weekly_labour_budget_cents
    lines.append("")
    lines.append(
        f"Week: {len(shifts)} shifts, {hours_label(total_paid)} paid hours, "
        f"labour {money(total)}, budget {money(budget)}."
    )
    return "\n".join(lines)
