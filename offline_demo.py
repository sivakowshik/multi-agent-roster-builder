"""Run the roster build with no Azure credentials.

Walks the same tools the agents call, in the same order: draft, check,
repair or trim, check again. The path is fixed, so the output does not change
between machines.
"""

from __future__ import annotations

from roster_builder.report import format_roster
from roster_builder.scripted import format_trace, run_scripted
from roster_builder.tools import board


def main() -> None:
    result = run_scripted()
    print(format_trace(result), end="")
    venue, shifts = board()
    print()
    print(format_roster(venue, shifts))
    print()
    print(f"stop: {result['stop']}")


if __name__ == "__main__":
    main()
