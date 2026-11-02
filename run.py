"""Run the roster team against Azure OpenAI. Re-checks the result in Python."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from autogen_agentchat.ui import Console

from roster_builder.agents import build_team, make_model_client
from roster_builder.config import MissingConfig, load_settings
from roster_builder.report import format_roster
from roster_builder.tools import board, check_compliance, check_labour_cost, reset_board

TASK = """Build next week's roster for Helio Grill, a fictional sample venue.

Hourly foot-traffic counts are already loaded. They are sample entry totals in the shape a CCTV people-counter would export. You cannot see video.

Use your tools. Compliance and cost will check the roster. Those checks are Python. When both have passed and coverage_gaps is empty, reply with exactly:
ROSTER_ACCEPTED

Sample rules are not legal advice and not an award interpretation."""


def _mentions(result, text: str) -> bool:
    for message in result.messages:
        source = getattr(message, "source", "")
        if source != "planner":
            continue
        body = message.to_text() if hasattr(message, "to_text") else str(getattr(message, "content", ""))
        if text in body:
            return True
    return False


async def run(max_messages: int) -> int:
    settings = load_settings()
    reset_board()
    client = make_model_client(settings)
    team = build_team(client, max_messages=max_messages)
    print(f"Azure deployment {settings.deployment} ({settings.model}). Tools own the numbers.\n")
    try:
        result = await Console(team.run_stream(task=TASK))
    finally:
        await client.close()

    compliance = json.loads(check_compliance())
    cost = json.loads(check_labour_cost())
    venue, shifts = board()
    model_accepted = _mentions(result, "ROSTER_ACCEPTED")
    verified = compliance["passed"] and cost["passed"] and not compliance["coverage_gaps"]
    print("\nPython re-check (ignores the model's wording):")
    print(f"  compliance {compliance['verdict']}  ({compliance['violation_count']} violations)")
    print(f"  cost {cost['verdict']}  labour {cost['labour_cost']}  budget {cost['weekly_budget']}  {cost['delta_label']}")
    print(f"  coverage gaps {len(compliance['coverage_gaps'])}")
    if model_accepted and not verified:
        print("  The planner said ROSTER_ACCEPTED but the tools do not. Treat the roster as not accepted.")
    print(f"  accepted {str(verified).lower()}")
    print()
    print(format_roster(venue, shifts))
    return 0 if verified else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a weekly roster with the AutoGen team (Azure OpenAI).")
    parser.add_argument("--max-messages", type=int, default=16, help="Stop after this many team messages.")
    args = parser.parse_args()
    try:
        code = asyncio.run(run(args.max_messages))
    except MissingConfig as exc:
        print(exc, file=sys.stderr)
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
