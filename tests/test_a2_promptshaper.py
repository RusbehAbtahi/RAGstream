from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ragstream.agents.a2_promptshaper import A2PromptShaper
from ragstream.orchestration.super_prompt import SuperPrompt


class _FakeAgent:
    def __init__(self) -> None:
        self.model_name = "gpt-test"
        self.temperature = 0.2
        self.max_output_tokens = 180
        self.option_labels = {
            "system": {"consultant": "Consultant"},
            "audience": {"dev_team": "Developer Team"},
            "tone": {"concise": "Concise"},
            "depth": {"high": "High"},
            "confidence": {"medium": "Medium"},
        }
        self.compose_called_with = None

    def compose(self, *, input_payload, active_fields):
        self.compose_called_with = {
            "input_payload": input_payload,
            "active_fields": active_fields,
        }
        return [{"role": "system", "content": "shape"}], {"type": "json_object"}


class _FakeFactory:
    def __init__(self, agent):
        self._agent = agent
        self.calls = []

    def get_agent(self, *, agent_id, version):
        self.calls.append({"agent_id": agent_id, "version": version})
        return self._agent


class _FakeLLMClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _make_super_prompt() -> SuperPrompt:
    sp = SuperPrompt(stage="preprocessed")
    sp.body["task"] = "Summarize risks"
    sp.body["context"] = "Q2 planning"
    sp.body["purpose"] = "Leadership update"
    return sp


def test_a2_promptshaper_updates_superprompt_and_stage_tracking() -> None:
    agent = _FakeAgent()
    factory = _FakeFactory(agent)
    llm = _FakeLLMClient(
        {
            "system": "consultant",
            "audience": "dev_team",
            "tone": "concise",
            "depth": "high",
            "confidence": "medium",
        }
    )
    shaper = A2PromptShaper(agent_factory=factory, llm_client=llm)

    sp = _make_super_prompt()
    out = shaper.run(sp)

    assert out is sp
    assert factory.calls == [{"agent_id": "a2_promptshaper", "version": "002"}]
    assert agent.compose_called_with is not None
    assert agent.compose_called_with["input_payload"] == {
        "task": "Summarize risks",
        "context": "Q2 planning",
        "purpose": "Leadership update",
    }
    assert llm.calls[0]["model_name"] == "gpt-test"
    assert llm.calls[0]["temperature"] == 0.2
    assert llm.calls[0]["max_output_tokens"] == 180

    assert sp.body["system"] == "Consultant"
    assert sp.body["audience"] == "Developer Team"
    assert sp.body["tone"] == "Concise"
    assert sp.body["depth"] == "High"
    assert sp.body["confidence"] == "Medium"
    assert sp.extras["a2_selected_ids"]["tone"] == "concise"
    assert sp.stage == "a2"
    assert sp.history_of_stages[-1] == "a2"
    assert "## SYSTEM" in sp.prompt_ready
    assert "## TASK" in sp.prompt_ready


def test_a2_promptshaper_accepts_json_string_response() -> None:
    agent = _FakeAgent()
    factory = _FakeFactory(agent)
    llm = _FakeLLMClient(
        '{"system":"consultant","audience":"dev_team","tone":"concise","depth":"high","confidence":"medium"}'
    )
    shaper = A2PromptShaper(agent_factory=factory, llm_client=llm)

    sp = _make_super_prompt()
    shaper.run(sp)

    assert sp.body["tone"] == "Concise"
    assert sp.extras["a2_selected_ids"]["system"] == "consultant"


def test_a2_promptshaper_raises_on_invalid_json() -> None:
    agent = _FakeAgent()
    factory = _FakeFactory(agent)
    llm = _FakeLLMClient("not-json")
    shaper = A2PromptShaper(agent_factory=factory, llm_client=llm)

    sp = _make_super_prompt()
    with pytest.raises(RuntimeError, match="did not return valid JSON"):
        shaper.run(sp)
