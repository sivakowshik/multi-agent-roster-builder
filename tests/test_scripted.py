"""The offline team path: same tools, fixed order, no credentials."""

from roster_builder.rules import compliance_violations, cost_report, coverage_gaps
from roster_builder.scripted import run_scripted
from roster_builder.tools import board, reset_board


def test_scripted_week_is_accepted_and_repeatable():
    first = run_scripted()
    venue, _ = board()
    assert first["accepted"] is True
    assert first["stop"] == "ROSTER_ACCEPTED"
    assert compliance_violations(venue, first["shifts"]) == []
    assert coverage_gaps(venue, first["shifts"]) == []
    report = cost_report(venue, first["shifts"])
    assert report["passed"] is True

    second = run_scripted()
    key = lambda shifts: [(s.staff_id, s.day, s.start, s.end, s.break_minutes) for s in shifts]
    assert key(first["shifts"]) == key(second["shifts"])

    speakers = [(event["speaker"], event["kind"]) for event in first["trace"]]
    assert speakers[0] == ("planner", "staffing_needs")
    assert speakers[1] == ("planner", "draft_roster")
    assert ("compliance", "check_compliance") in speakers
    assert ("cost", "check_labour_cost") in speakers
    assert speakers[-1] == ("planner", "message")
    # The first compliance check should actually fail, otherwise the loop is theatre.
    first_check = next(event for event in first["trace"] if event["kind"] == "check_compliance")
    assert first_check["payload"]["passed"] is False


def test_tools_do_not_require_env(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    reset_board()
    result = run_scripted()
    assert result["accepted"] is True
