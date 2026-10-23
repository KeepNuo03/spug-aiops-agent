"""Agent Gateway FastAPI entrypoint."""

import asyncio
import json
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from alerts import AlertmanagerPayload, to_events
from incidents import Incident, store
from observability.structured_log import get_logger, log_event
from processing import handle_alert, skip_reason

FRONTEND = Path(__file__).parent / "frontend"
HEARTBEAT_SECONDS = 15

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


@app.get("/api/incidents")
def list_incidents() -> list[Incident]:
    return store.list()


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str) -> Incident:
    incident = store.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="no such incident")
    return incident


async def incident_events():
    """Server-sent events: one message per incident change, so the page never polls."""
    queue = store.subscribe()
    try:
        while True:
            try:
                incident = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield f"data: {json.dumps(incident.model_dump(mode='json'))}\n\n"
    finally:
        store.unsubscribe(queue)


@app.get("/api/stream")
async def stream_incidents() -> StreamingResponse:
    return StreamingResponse(incident_events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
