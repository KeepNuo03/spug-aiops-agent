"""LLM call for root-cause analysis.

DeepSeek speaks the OpenAI protocol, so the OpenAI SDK is used directly rather than a framework
wrapper. Temperature is 0 so the same evidence yields the same answer, and the reply must be JSON
matching Diagnosis — a reply that does not parse is retried once before the step gives up.
"""

import json
import os

from openai import AsyncOpenAI
from pydantic import ValidationError

from diagnosis.models import Diagnosis

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-pro")
TIMEOUT = float(os.environ.get("LLM_TIMEOUT_SECONDS", 60))

SYSTEM_PROMPT = """You are a Linux SRE diagnosing a production alert.

Rules:
- Use only the evidence given. Never invent process names, PIDs or numbers.
- Every claim must come from a probe; list the probe names you used in evidence_used.
- If a probe is UNAVAILABLE or the evidence does not explain the alert, say so in root_cause and
  lower your confidence. An honest "cannot determine from this evidence" beats a guess.
- Actions are proposals. A human approves them before anything runs, so propose the smallest
  action that addresses the cause, and only when the evidence identifies a culprit.
- Use "kill" with a pid you can see in the evidence when a single process is at fault. When many
  processes share one name and all of them must go, use "kill_by_name" with that exact name.
  For anything else use "manual" and put the command an engineer should run in the command field.
- Propose an executable action first when the evidence supports one; a manual command the operator
  has to retype is a worse answer than a precise action they can approve.

Reply with JSON only, matching this schema:
{
  "root_cause": "one sentence",
  "summary": "two or three sentences for the on-call engineer",
  "confidence": 0.0 to 1.0,
  "evidence_used": ["probe_name", ...],
  "culprit_process": {"name": "...", "pid": 123, "cpu_percent": 99.9} or null,
  "actions": [
    {"action": "kill", "pid": 123, "reason": "why this ends the incident"},
    {"action": "kill_by_name", "process_name": "stress-ng", "reason": "why all of them must go"},
    {"action": "manual", "command": "...", "reason": "what an engineer should check or do"}
  ]
}"""

USER_PROMPT = """## Alert
host: {host}
alert: {alertname}
summary: {summary}
detail: {description}
started: {starts_at}

## Evidence
{evidence}"""


def _client() -> AsyncOpenAI:
    if not API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    return AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=TIMEOUT)


def build_prompt(event, evidence_block: str) -> str:
    return USER_PROMPT.format(
        host=event.hostname or "unknown",
        alertname=event.alertname,
        summary=event.summary,
        description=event.description,
        starts_at=event.starts_at.isoformat(),
        evidence=evidence_block,
    )


async def diagnose(prompt: str) -> Diagnosis:
    client = _client()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]

    for attempt in range(2):
        response = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        reply = response.choices[0].message.content or ""
        try:
            return Diagnosis.model_validate(json.loads(reply))
        except (json.JSONDecodeError, ValidationError) as exc:
            if attempt == 1:
                raise RuntimeError(f"model did not return a valid diagnosis: {exc}") from exc
            messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"That did not match the schema ({exc}). Reply with valid JSON only."},
            ]
    raise AssertionError("unreachable")
