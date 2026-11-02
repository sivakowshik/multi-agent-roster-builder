"""Deterministic stand-in for the team chat. Same tools, no model, no keys."""

from __future__ import annotations

import json

from roster_builder.tools import (
    board,
    check_compliance,
    check_labour_cost,
    draft_roster,
    repair_compliance,
    reset_board,
    staffing_needs,
    trim_to_budget,
)


def run_scripted(max_cycles: int = 4) -> dict:
    reset_board()
    trace = []

    def record(speaker: str, kind: str, raw: str | dict) -> dict:
        payload = json.loads(raw) if isinstance(raw, str) else raw
        event = {"speaker": speaker, "kind": kind, "payload": payload}
        trace.append(event)
        return payload

    record("planner", "staffing_needs", staffing_needs())
    record("planner", "draft_roster", draft_roster())

    accepted = False
    stop = "round limit"
    for cycle in range(max_cycles):
        compliance = record("compliance", "check_compliance", check_compliance())
        cost = record("cost", "check_labour_cost", check_labour_cost())
        gaps = compliance["coverage_gaps"]
        if compliance["passed"] and cost["passed"] and not gaps:
            record("planner", "message", {"text": "ROSTER_ACCEPTED"})
            accepted = True
            stop = "ROSTER_ACCEPTED"
            break
        if cycle == max_cycles - 1:
            record("planner", "message", {"text": "ROSTER_STOPPED"})
            break
        _, shifts = board()
        before = tuple(sorted((s.staff_id, s.day, s.start, s.end, s.break_minutes) for s in shifts))
        if not compliance["passed"] or gaps:
            record("planner", "repair_compliance", repair_compliance())
        else:
            record("planner", "trim_to_budget", trim_to_budget())
        _, shifts = board()
        after = tuple(sorted((s.staff_id, s.day, s.start, s.end, s.break_minutes) for s in shifts))
        if after == before:
            record("planner", "message", {"text": "ROSTER_STOPPED", "detail": "tool made no change"})
            stop = "no change"
            break

    _, shifts = board()
    return {"accepted": accepted, "stop": stop, "trace": trace, "shifts": list(shifts)}


def format_trace(result: dict) -> str:
    lines = ["Helio Grill weekly roster. Fictional sample data. No Azure calls.", ""]
    for event in result["trace"]:
        speaker = event["speaker"]
        kind = event["kind"]
        payload = event["payload"]
        if kind == "staffing_needs":
            lines.append(f"{speaker} -> staffing_needs")
            for row in payload["busiest"]:
                lines.append(
                    f"  {row['day']:<10} busiest {row['hour']}  entries {row['entries']:<3} "
                    f"front {row['front']}  kitchen {row['kitchen']}"
                )
        elif kind == "draft_roster":
            lines.append(f"{speaker} -> draft_roster")
            lines.append(
                f"  {payload['shift_count']} shifts, {payload['paid_hours']} paid hours, "
                f"{payload['cost']} before rule repair"
            )
            gaps = payload["coverage_gaps"]
            if gaps:
                lines.append(f"  coverage gaps: {len(gaps)}")
        elif kind == "check_compliance":
            lines.append(f"{speaker} -> check_compliance  {payload['verdict']}")
            for item in payload["violations"]:
                lines.append(f"  - {item['message']}")
            if not payload["violations"]:
                lines.append("  - none")
        elif kind == "check_labour_cost":
            lines.append(f"{speaker} -> check_labour_cost  {payload['verdict']}")
            lines.append(
                f"  labour {payload['labour_cost']}  budget {payload['weekly_budget']}  {payload['delta_label']}"
            )
        elif kind in {"repair_compliance", "trim_to_budget"}:
            lines.append(f"{speaker} -> {kind}")
            for action in payload["actions"]:
                lines.append(f"  - {action}")
        elif kind == "message":
            lines.append(f"{speaker}: {payload['text']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
