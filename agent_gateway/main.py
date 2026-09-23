"""Agent Gateway FastAPI entrypoint."""

from fastapi import BackgroundTasks, FastAPI

from alerts import AlertmanagerPayload, to_events
from observability.structured_log import get_logger, log_event
from processing import handle_alert, skip_reason

app = FastAPI(title="spug-aiops-agent gateway")
log = get_logger("agent_gateway")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/webhook/alertmanager")
async def alertmanager_webhook(payload: AlertmanagerPayload, background: BackgroundTasks) -> dict:
    accepted = 0
    for event in to_events(payload):
        log_event(log, "alert_received", **event.model_dump(mode="json", exclude={"labels"}))
        reason = skip_reason(event)
        if reason:
            log_event(log, "alert_skipped", fingerprint=event.fingerprint, reason=reason)
            continue
        background.add_task(handle_alert, event)
        accepted += 1
    return {"received": len(payload.alerts), "accepted": accepted}
