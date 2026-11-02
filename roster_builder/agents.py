"""Three AgentChat assistants. Round robin, because the review order is fixed.

reflect_on_tool_use is off so the team sees the tool JSON, not a paraphrase
of the dollars and the violations.
"""

from __future__ import annotations

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

from roster_builder.config import Settings
from roster_builder.tools import (
    check_compliance,
    check_labour_cost,
    draft_roster,
    repair_compliance,
    staffing_needs,
    trim_to_budget,
)

PLANNER_TOOLS = [staffing_needs, draft_roster, repair_compliance, trim_to_budget]
COMPLIANCE_TOOLS = [check_compliance]
COST_TOOLS = [check_labour_cost]

PLANNER_MESSAGE = """You build the weekly roster. You do not invent counts, hours, or dollars.

First turn: call staffing_needs, then draft_roster.
Later turns, read the latest compliance and cost messages. They are tool JSON.
- If compliance passed is false, or coverage_gaps is not empty, call repair_compliance once.
- If compliance passed is true, coverage_gaps is empty, and cost passed is false, call trim_to_budget once.
- If compliance passed is true, cost passed is true, and coverage_gaps is empty, do not call a tool. Reply with exactly: ROSTER_ACCEPTED
- If a repair or trim result says it made no change and the checks still fail, reply with exactly: ROSTER_STOPPED

The sample rules are not legal advice and not an award interpretation. Quote figures from tool JSON only."""

COMPLIANCE_MESSAGE = """You check the current roster against the sample house rules.
Call check_compliance once and stop. Do not rewrite the roster. Do not give legal advice.
The tool JSON is the verdict."""

COST_MESSAGE = """You check labour cost against the weekly budget.
Call check_labour_cost once and stop. Do not adjust the figure. The tool JSON is the verdict."""


def make_model_client(settings: Settings) -> AzureOpenAIChatCompletionClient:
    # azure_endpoint is the resource root, e.g. https://name.openai.azure.com
    # azure_deployment is the deployment name; model is what AgentChat uses for
    # capability lookup (tool calling). temperature 0 because the roster should
    # not drift between runs when the tools already decide the numbers.
    return AzureOpenAIChatCompletionClient(
        model=settings.model,
        azure_endpoint=settings.endpoint,
        azure_deployment=settings.deployment,
        api_version=settings.api_version,
        api_key=settings.api_key,
        temperature=0,
    )


def build_team(model_client, max_messages: int = 16) -> RoundRobinGroupChat:
    planner = AssistantAgent(
        name="planner",
        description="Turns hourly foot traffic into a draft roster and revises it after the checkers.",
        model_client=model_client,
        tools=PLANNER_TOOLS,
        system_message=PLANNER_MESSAGE,
        reflect_on_tool_use=False,
        max_tool_iterations=3,
    )
    compliance = AssistantAgent(
        name="compliance",
        description="Checks the current roster against the sample shift rules by calling a Python tool.",
        model_client=model_client,
        tools=COMPLIANCE_TOOLS,
        system_message=COMPLIANCE_MESSAGE,
        reflect_on_tool_use=False,
        max_tool_iterations=1,
    )
    cost = AssistantAgent(
        name="cost",
        description="Checks base-rate labour cost against the weekly budget by calling a Python tool.",
        model_client=model_client,
        tools=COST_TOOLS,
        system_message=COST_MESSAGE,
        reflect_on_tool_use=False,
        max_tool_iterations=1,
    )
    stop = (
        TextMentionTermination("ROSTER_ACCEPTED", sources=["planner"])
        | TextMentionTermination("ROSTER_STOPPED", sources=["planner"])
        | MaxMessageTermination(max_messages)
    )
    return RoundRobinGroupChat([planner, compliance, cost], termination_condition=stop)
