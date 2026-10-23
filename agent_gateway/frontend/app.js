const incidents = new Map();
let selectedId = null;

const listEl = document.getElementById("incident-list");
const emptyEl = document.getElementById("empty-list");
const detailEl = document.getElementById("detail");
const connectionEl = document.getElementById("connection");

const text = (value) => String(value ?? "");

function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = text(content);
  return node;
}

function clockTime(iso) {
  return new Date(iso).toLocaleTimeString();
}

function renderList() {
  const all = [...incidents.values()].sort((a, b) => b.opened_at.localeCompare(a.opened_at));
  emptyEl.hidden = all.length > 0;
  listEl.replaceChildren();

  for (const incident of all) {
    const item = el("li", `incident${incident.id === selectedId ? " selected" : ""}`);
    item.appendChild(el("div", "title", `${incident.alertname} · ${incident.hostname ?? "unknown host"}`));

    const meta = el("div", "meta");
    meta.appendChild(el("span", `badge status-${incident.status}`, incident.status));
    meta.appendChild(el("span", null, clockTime(incident.opened_at)));
    item.appendChild(meta);

    item.addEventListener("click", () => {
      selectedId = incident.id;
      renderList();
      renderDetail();
    });
    listEl.appendChild(item);
  }
}

function renderDiagnosis(diagnosis) {
  const nodes = [];
  const card = el("div", "card");
  card.appendChild(el("div", "label", "root cause"));
  card.appendChild(el("p", null, diagnosis.root_cause));
  card.appendChild(el("p", "muted", diagnosis.summary));

  const kv = el("div", "kv");
  kv.appendChild(el("span", "badge", `confidence ${diagnosis.confidence}`));
  kv.appendChild(
    el("span", `badge ${diagnosis.verified ? "live" : "down"}`, diagnosis.verified ? "verified" : "not verified"),
  );
  if (diagnosis.culprit_process) {
    const p = diagnosis.culprit_process;
    kv.appendChild(el("span", "badge", `${p.name}${p.pid ? ` (pid ${p.pid})` : ""}`));
  }
  if (diagnosis.latency_ms) kv.appendChild(el("span", "badge", `${(diagnosis.latency_ms / 1000).toFixed(1)}s`));
  card.appendChild(kv);
  if (diagnosis.verification_note) card.appendChild(el("p", "muted", diagnosis.verification_note));
  nodes.push(card);

  if (diagnosis.evidence_used?.length) {
    const cited = el("div", "card");
    cited.appendChild(el("div", "label", "evidence cited"));
    cited.appendChild(el("p", null, diagnosis.evidence_used.join(", ")));
    nodes.push(cited);
  }

  return nodes;
}

async function decide(incidentId, decision, actionIndex) {
  await fetch(`/api/incidents/${incidentId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, action_index: actionIndex ?? null }),
  });
}

function renderApproval(incident) {
  const approval = incident.approval;
  const expired = new Date(approval.expires_at) <= new Date();
  const pending = incident.status === "awaiting_approval" && !expired;
  const heading = incident.status === "awaiting_approval" && expired ? "Approval expired" : "Proposed remediation";
  const nodes = [el("h3", null, pending ? "Awaiting approval" : heading)];

  for (const proposed of approval.actions) {
    const card = el("div", "card");
    card.appendChild(el("div", "command", proposed.command ?? proposed.action.action));
    card.appendChild(el("p", "muted", proposed.action.reason));

    const kv = el("div", "kv");
    kv.appendChild(el("span", `badge risk-${proposed.risk}`, proposed.risk));
    if (proposed.blocked_reason) kv.appendChild(el("span", "badge", `not executable: ${proposed.blocked_reason}`));
    if (expired && proposed.executable) kv.appendChild(el("span", "badge", "expired — run it yourself if still needed"));
    card.appendChild(kv);

    if (pending && proposed.executable) {
      const actions = el("div", "kv");
      const approve = el("button", "btn approve", "Approve and run");
      approve.addEventListener("click", () => decide(incident.id, "approve", proposed.index));
      const reject = el("button", "btn reject", "Reject");
      reject.addEventListener("click", () => decide(incident.id, "reject", proposed.index));
      actions.append(approve, reject);
      card.appendChild(actions);
    }
    nodes.push(card);
  }
  return nodes;
}

function summarizeSeries(series) {
  return series
    .map((entry) => {
      const host = entry.labels?.hostname ?? entry.labels?.instance ?? "?";
      if (entry.value !== undefined) return `${host}: ${entry.value.toFixed(2)}`;
      const values = (entry.samples ?? []).map((s) => s.value);
      if (!values.length) return `${host}: no samples`;
      const avg = values.reduce((a, b) => a + b, 0) / values.length;
      const trend =
        values.at(-1) > values[0] * 1.1 ? "rising" : values.at(-1) < values[0] * 0.9 ? "falling" : "steady";
      return `${host}: current ${values.at(-1).toFixed(1)}, peak ${Math.max(...values).toFixed(1)}, average ${avg.toFixed(1)} — ${trend} over ${values.length} samples`;
    })
    .join("\n");
}

function renderEvidence(evidence) {
  const nodes = [el("h3", null, "Evidence")];
  for (const item of evidence) {
    const probe = el("div", "probe");
    probe.appendChild(el("div", `name${item.error ? " failed" : ""}`, item.probe));
    if (item.error) {
      probe.appendChild(el("p", "muted", item.error));
    } else if (item.result?.output !== undefined) {
      probe.appendChild(el("div", "command", `$ ${item.result.command}`));
      probe.appendChild(el("pre", null, item.result.output || "(no output)"));
    } else if (item.result?.series) {
      probe.appendChild(el("div", "command", item.result.query));
      probe.appendChild(el("pre", null, summarizeSeries(item.result.series)));
    } else {
      probe.appendChild(el("pre", null, JSON.stringify(item.result, null, 2)));
    }
    nodes.push(probe);
  }
  return nodes;
}

function renderDetail() {
  const incident = incidents.get(selectedId);
  if (!incident) {
    detailEl.replaceChildren(el("p", "muted", "Select an incident to see how it was handled."));
    return;
  }

  const nodes = [];
  const heading = el("h2", null, `${incident.alertname} · ${incident.hostname ?? "unknown host"}`);
  nodes.push(heading, el("p", "muted", incident.summary));

  const kv = el("div", "kv");
  kv.appendChild(el("span", `badge status-${incident.status}`, incident.status));
  if (incident.intent) kv.appendChild(el("span", "badge", `intent ${incident.intent}`));
  kv.appendChild(el("span", "badge", `opened ${clockTime(incident.opened_at)}`));
  nodes.push(kv);

  if (incident.diagnosis) {
    nodes.push(el("h3", null, "Diagnosis"));
    nodes.push(...renderDiagnosis(incident.diagnosis));
  }

  if (incident.approval?.actions?.length) nodes.push(...renderApproval(incident));

  nodes.push(el("h3", null, "Timeline"));
  const timeline = el("ul", "timeline");
  for (const entry of incident.timeline) {
    const li = el("li");
    li.appendChild(el("div", "event", entry.event));
    if (entry.detail) li.appendChild(el("div", "detail", entry.detail));
    li.appendChild(el("div", "at", clockTime(entry.at)));
    timeline.appendChild(li);
  }
  nodes.push(timeline);

  if (incident.evidence?.length) nodes.push(...renderEvidence(incident.evidence));

  detailEl.replaceChildren(...nodes);
}

function upsert(incident) {
  incidents.set(incident.id, incident);
  if (selectedId === null) selectedId = incident.id;
  renderList();
  if (incident.id === selectedId) renderDetail();
}

async function loadInitial() {
  const response = await fetch("/api/incidents");
  for (const incident of await response.json()) incidents.set(incident.id, incident);
  if (incidents.size && selectedId === null) selectedId = [...incidents.values()][0].id;
  renderList();
  renderDetail();
}

function connect() {
  const source = new EventSource("/api/stream");
  source.onopen = () => {
    connectionEl.textContent = "live";
    connectionEl.className = "badge live";
  };
  source.onmessage = (message) => upsert(JSON.parse(message.data));
  source.onerror = () => {
    connectionEl.textContent = "reconnecting…";
    connectionEl.className = "badge down";
  };
}

loadInitial().then(connect);
