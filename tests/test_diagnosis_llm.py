import json

import pytest

from diagnosis import llm
from diagnosis.llm import build_prompt, diagnose

VALID_REPLY = json.dumps(
    {
        "root_cause": "stress-ng saturates every core",
        "summary": "Four workers are pinning the CPU.",
        "confidence": 0.95,
        "evidence_used": ["top_processes"],
        "culprit_process": {"name": "stress-ng", "pid": 344, "cpu_percent": 100.0},
        "actions": [{"action": "kill", "pid": 344, "reason": "stop the load generator"}],
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
    assert answer.actions[0].action == "kill"
    assert answer.actions[0].pid == 344


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


def test_prompt_carries_alert_context_and_evidence(make_event):
    prompt = build_prompt(make_event(), "### top_processes\n344 stress-ng")
    assert "lab-host" in prompt
    assert "HostHighCpuUsage" in prompt
    assert "344 stress-ng" in prompt


async def test_the_language_rule_reaches_the_model(fake_llm, monkeypatch):
    monkeypatch.setattr(llm, "LANGUAGE", "zh")
    completions = fake_llm(VALID_REPLY)
    await diagnose("prompt")

    system = completions.requests[0]["messages"][0]["content"]
    assert "Simplified Chinese" in system
    # Process names and numbers have to survive untranslated, or the cross-check stops matching.
    assert "do not translate" in system


async def test_english_is_the_default(fake_llm, monkeypatch):
    monkeypatch.setattr(llm, "LANGUAGE", "en")
    completions = fake_llm(VALID_REPLY)
    await diagnose("prompt")
    assert "in English" in completions.requests[0]["messages"][0]["content"]


async def test_an_unknown_language_falls_back_to_english(fake_llm, monkeypatch):
    monkeypatch.setattr(llm, "LANGUAGE", "klingon")
    completions = fake_llm(VALID_REPLY)
    await diagnose("prompt")
    assert "in English" in completions.requests[0]["messages"][0]["content"]


def test_missing_api_key_is_reported(monkeypatch):
    monkeypatch.setattr(llm, "API_KEY", "")
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        llm._client()
