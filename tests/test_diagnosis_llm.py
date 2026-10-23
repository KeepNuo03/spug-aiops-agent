import json

import pytest
from tests.test_intent import make_event

from diagnosis import llm
from diagnosis.llm import build_prompt, diagnose

VALID_REPLY = json.dumps(
    {
        "root_cause": "stress-ng saturates every core",
        "summary": "Four workers are pinning the CPU.",
        "confidence": 0.95,
        "evidence_used": ["top_processes"],
        "culprit_process": {"name": "stress-ng", "pid": 344, "cpu_percent": 100.0},
        "suggested_commands": [{"command": "kill -9 344", "reason": "stop the load generator"}],
    }
)


class FakeCompletions:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        reply = self.replies.pop(0)
        message = type("Message", (), {"content": reply})
        return type("Response", (), {"choices": [type("Choice", (), {"message": message})]})


@pytest.fixture
def fake_llm(monkeypatch):
    def serve(*replies):
        completions = FakeCompletions(replies)
        client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})})
        monkeypatch.setattr(llm, "_client", lambda: client)
        return completions

    return serve


async def test_valid_reply_is_parsed(fake_llm):
    fake_llm(VALID_REPLY)
    answer = await diagnose("prompt")
    assert answer.culprit_process.name == "stress-ng"
    assert answer.suggested_commands[0].command == "kill -9 344"


async def test_request_is_deterministic_and_json_only(fake_llm):
    completions = fake_llm(VALID_REPLY)
    await diagnose("prompt")
    request = completions.requests[0]
    assert request["temperature"] == 0
    assert request["response_format"] == {"type": "json_object"}


async def test_malformed_reply_is_retried_once(fake_llm):
    completions = fake_llm("not json at all", VALID_REPLY)
    answer = await diagnose("prompt")
    assert answer.confidence == 0.95
    assert len(completions.requests) == 2
    # The retry tells the model what was wrong instead of repeating the same request.
    assert "valid JSON" in completions.requests[1]["messages"][-1]["content"]


async def test_reply_missing_required_fields_is_retried(fake_llm):
    completions = fake_llm(json.dumps({"summary": "no root cause here"}), VALID_REPLY)
    await diagnose("prompt")
    assert len(completions.requests) == 2


async def test_two_bad_replies_raise(fake_llm):
    fake_llm("nope", "still nope")
    with pytest.raises(RuntimeError, match="valid diagnosis"):
        await diagnose("prompt")


def test_prompt_carries_alert_context_and_evidence():
    prompt = build_prompt(make_event(), "### top_processes\n344 stress-ng")
    assert "lab-host" in prompt
    assert "HostHighCpuUsage" in prompt
    assert "344 stress-ng" in prompt


def test_missing_api_key_is_reported(monkeypatch):
    monkeypatch.setattr(llm, "API_KEY", "")
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        llm._client()
