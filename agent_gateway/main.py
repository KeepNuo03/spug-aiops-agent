"""Agent Gateway FastAPI entrypoint."""

from fastapi import FastAPI

from alerts import AlertmanagerPayload, to_events
from observability.structured_log import get_logger, log_event

app = FastAPI(title="spug-aiops-agent gateway")
log = get_logger("agent_gateway")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/webhook/alertmanager")
def alertmanager_webhook(payload: AlertmanagerPayload) -> dict:
    events = to_events(payload)
    for event in events:
        log_event(log, "alert_received", **event.model_dump(mode="json", exclude={"labels"}))
    firing = sum(1 for event in events if event.status == "firing")
    return {"received": len(events), "firing": firing}
