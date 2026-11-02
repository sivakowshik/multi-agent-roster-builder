# Notes

Plain-English notes for if someone asks me about this repo in an interview. `README.md` is the short version.

## What this is, in one pass

A venue has hourly foot-traffic counts, a staff list, who can work when, who can open or close, and a base pay rate. The job is a weekly roster that covers those counts, follows a few house rules, and lands under a labour target.

I split that into three AutoGen agents because the failure should arrive as someone else's message. The planner drafts. Compliance says the draft broke a rule. Cost says it missed the budget. The planner then calls a repair tool or a trim tool. One agent with the same six tools would work. The team is there so the planner has to read a verdict it did not write.

The model does not own the numbers. Every count, shift, and dollar is a Python function. The model chooses which function to call, and when to stop.

## Why the draft does not insert meal breaks

`draft_roster` covers demand. It already respects availability, the weekly cap, and the rest gap, because those are easier to enforce while placing an hour than to unwind later. It does not insert the 30 minute break.

If the drafter also inserted breaks, compliance would pass on the first look every time and the team chat would be theatre. The checker is a second piece of code. `repair_compliance` is what actually edits the roster, and only after the checker has failed. On the sample week the only failure is those missing breaks: 15 shifts over 5 hours. Adding the unpaid 30 minutes drops labour from $7,381 to $7,167, which crosses the $7,300 target. That is 15 half hours. I checked the subtraction by hand before I trusted the demo.

I set $7,300 on purpose, between those two totals, so the cost agent has a fail to report. A real target would come from sales. I would not tune a production budget to make a demo look tidy, and I don't want to pretend this one wasn't placed there.

## Why round robin, and why the tool JSON is the message

`SelectorGroupChat` asks a model who should speak next. Here the order is always planner, then compliance, then cost. Paying for that choice can also skip the cost agent. `RoundRobinGroupChat` is the whole team pattern.

`reflect_on_tool_use` defaults to false when you are not using structured output, and I set it false explicitly. If it were true, the model would write a summary of the tool result and the other agents would see the summary. I want them to see `passed`, `verdict`, and the violation strings. Compliance and cost are each allowed one tool iteration, so they call the check and the call is their whole turn. They don't get a second inference in which to round a dollar.

The planner gets three tool iterations so it can call `staffing_needs` and then `draft_roster` in one turn. When both checks have passed it is told to call nothing and reply `ROSTER_ACCEPTED`. Termination listens for that string, and for `ROSTER_STOPPED`, and for 16 messages. Only the planner's messages count for the two phrases, so a tool result cannot stop the team by accident.

`run.py` still re-runs `check_compliance` and `check_labour_cost` after the team finishes. The roster lives in the process, and only tools mutate it, so the re-check is the same state the agents just looked at. If the model says accepted and the tools disagree, the script says so and exits 2.

## The tools and the board

`roster_builder/tools.py` holds the current list of shifts. The tools close over it. That is a bit of global state, which I would not do in a service with two builds in flight. For one CLI run it is the least machinery that lets the compliance agent check "the roster" without the model pasting 50 shifts back as an argument. Models drop rows when you make them do that.

`offline_demo.py` and the tests call those same functions. There is no second implementation of the rules hiding in the demo.

## How a shift gets built

`draft.py` walks Monday to Sunday, hour by hour, front then kitchen.

For each hour it ranks people who are free, under their weekly cap, and not about to break the 10 hour rest gap. A missing opener or closer outranks everything else on that hour, then someone already working the neighbouring hour, then the cheaper rate, then the id so the sort never depends on dict order. If the only way to cover the hour is to bridge a hole in someone's day, it fills the hole, but only when the filled block still passes rest and the cap.

A new block is grown out to 3 hours or not placed. Otherwise the draft is full of 1 hour shifts and repair spends its time undoing them. Growing a 1 hour peak out to 3 hours does overstaff the shoulder. That is the cost of the minimum-shift rule, and trim will only take those hours back if they are a true surplus edge and the budget actually failed.

`repair_shifts` then bridges any same-day split closer than 10 hours, fills whatever demand is left, places an opener and a closer if the draft missed them, drops anything still under 3 hours, shaves anyone over their weekly cap, and only then writes the meal breaks. Breaks are applied when the shifts are built, from the span, so they cannot drift out of sync with the hours.

`trim_shifts` removes one edge hour at a time, highest rate first, and refuses the cut if the block would fall under 3 hours, if demand would be missed, if rest would break, or if that person is the only opener or closer on that hour. On this sample week it is not needed. `tests/test_draft.py` forces a tiny budget so the cut still has a test.

Money is integer cents. `paid minutes * rate cents // 60`. Rates are in whole cents and breaks are 30 minutes, so it lands on a cent. I didn't want a float total that the test has to compare with `pytest.approx`.

## The close rule

`can_close` on a kitchen person does not count. The check looks for a front person, on shift at 21:00, with the flag. Hannah Okonkwo is `can_close=yes` and `area=kitchen` so a reader can see the distinction fail a unit test. The close is a front-of-house lockup, which is how I treated it as a manager. It is still a house rule I wrote, not an award clause.

Hours are half-open. `17:00-22:00` covers 17, 18, 19, 20 and 21. The 21:00 close is inside that shift. Availability uses the same convention: `until_hour` is the hour they are no longer available.

## The data

All of it is invented. `data/FICTIONAL.txt` says so in the folder itself, because a CSV of names and rates looks real if you only open that file.

`foot_traffic.csv` is 7 days by 11 hours, 11:00 through 21:00. Busy Friday and Saturday dinner, a weekday lunch peak, a quiet late afternoon. That lull is why some kitchen shifts stop mid-afternoon and someone else takes dinner, instead of one person being split across a 2 hour gap. A split closer than 10 hours is illegal under the sample rest rule, so the drafter bridges it or gives the second block to someone else.

Caps are high enough that Sunday still has people left. The fill walks Monday first and will not save hours for later. If I had left Jonah on 24 hours he would have been full by Saturday night and Sunday lunch would have been short. I would rather show a covered week than a clever failure.

Pay rates are base rates around the mid twenties to mid thirties. They are not award rates.

## Files

`roster_builder/data.py` loads the four CSVs and `rules.json` into frozen dataclasses. Duplicate staff ids and missing traffic hours raise. I would rather fail at startup than roster a day that has no close.

`roster_builder/rules.py` is the checker. Headcount, violations, and the cost report. No I/O. The tests build tiny venues in memory so a regression in the sample week cannot hide a broken rest-gap check.

`roster_builder/draft.py` is the editor. It returns new shift lists. It does not print and it does not know about agents.

`roster_builder/tools.py` is the agent-facing JSON. Docstrings are one line because AgentChat uses the docstring as the tool description.

`roster_builder/scripted.py` is the offline team. Same order as the round robin: draft, check, check, repair or trim, repeat, stop when both pass or a tool makes no change or four cycles are used. `offline_demo.py` prints that trace and the table.

`roster_builder/agents.py` wires the three `AssistantAgent`s. `make_model_client` is the Azure client: resource endpoint, deployment name, api version, key, and `temperature=0`. The endpoint is the resource root, with no `/openai/v1` suffix. That suffix is the OpenAI SDK's v1 base URL, and `AzureOpenAIChatCompletionClient` in 0.7.5 does not want it. I checked the constructor on the installed package rather than copying a URL across from another project.

`roster_builder/config.py` reads `.env`. Missing variables exit with the names, not a traceback, and point at `offline_demo.py`.

`roster_builder/report.py` is the markdown table both entry points print, so the offline demo and `run.py` cannot drift.

`run.py` is the Azure path. `tests/test_team.py` builds the team with a fake client that only supplies `model_info`, because `AssistantAgent` checks `function_calling` at init and does not call the network until `run`.

## What I would say if asked "does the model build the roster?"

It decides the loop. It does not decide the hours. I have watched a model drop a closer while "fixing" a break, so the edit tools are deterministic and tested. The next step, once I have evals, is to let the planner propose a shift list and reject it with the same checker. I don't want to do that until I can show it stops making the roster worse.

## AutoGen

The `microsoft/autogen` GitHub repository is archived. The packages still install. I pinned 0.7.5 and imported the symbols the stable AgentChat docs describe: `AssistantAgent`, `RoundRobinGroupChat`, `TextMentionTermination`, `MaxMessageTermination`, `AzureOpenAIChatCompletionClient`. A test imports them so a future install that renamed the API fails loudly. I would not take a dependency on an archived framework for a product. The thing I would keep is the split: agents decide, Python checks.

## What this is not

It does not watch CCTV. It does not apply the Fast Food Award or any agreement. It is not an optimiser. Ben Walsh's Saturday is 11 hours because he is cheap and already on the neighbouring hour, and nothing in the sample rules forbids a day that long. That is the first rule I would add.
