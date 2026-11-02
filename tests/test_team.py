"""AgentChat wiring. Builds the team with a fake client; no network."""

import pytest

from roster_builder.agents import COST_TOOLS, PLANNER_TOOLS, build_team
from roster_builder.config import MissingConfig, load_settings


def test_current_agentchat_api_imports():
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
    from autogen_agentchat.teams import RoundRobinGroupChat
    from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

    assert AssistantAgent.__name__ == "AssistantAgent"
    assert RoundRobinGroupChat.__name__ == "RoundRobinGroupChat"
    assert MaxMessageTermination.__name__
    assert TextMentionTermination.__name__
    assert AzureOpenAIChatCompletionClient.__name__


def test_team_shape():
    class FakeClient:
        model_info = {
            "function_calling": True,
            "vision": False,
            "json_output": False,
            "family": "unknown",
            "structured_output": False,
        }

    team = build_team(FakeClient(), max_messages=16)
    names = [participant.name for participant in team._participants]
    assert names == ["planner", "compliance", "cost"]
    planner, compliance, cost = team._participants
    assert [tool.name for tool in planner._tools] == [tool.__name__ for tool in PLANNER_TOOLS]
    assert [tool.name for tool in compliance._tools] == ["check_compliance"]
    assert [tool.name for tool in cost._tools] == [fn.__name__ for fn in COST_TOOLS]
    assert planner._reflect_on_tool_use is False
    assert compliance._max_tool_iterations == 1


def test_missing_env_is_a_clean_error(monkeypatch):
    for name in (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir("/tmp")
    with pytest.raises(MissingConfig) as caught:
        load_settings()
    message = str(caught.value)
    assert "AZURE_OPENAI_API_KEY" in message
    assert "offline_demo.py" in message
