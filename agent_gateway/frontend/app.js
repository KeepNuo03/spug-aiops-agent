import { LANGUAGE_LABEL, LANGUAGES, dict } from "/static/i18n.js";

const incidents = new Map();
let selectedId = null;
let language = localStorage.getItem("language") ?? (navigator.language?.startsWith("zh") ? "zh" : "en");
let t = dict(language);

const listEl = document.getElementById("incident-list");
const emptyEl = document.getElementById("empty-list");
const countEl = document.getElementById("incident-count");
const detailEl = document.getElementById("detail");
const connectionEl = document.getElementById("connection");
const themeButton = document.getElementById("theme-toggle");
const languageButton = document.getElementById("language-toggle");

const STATUS_TONE = {
  received: "warn",
  classified: "warn",
  collecting: "warn",
  diagnosing: "warn",
  awaiting_approval: "info",
  executing: "warn",
  completed: "good",
  unresolved: "bad",
  expired: "muted",
  skipped: "muted",
  failed: "bad",
};
const LIVE_STATUSES = new Set(["received", "classified", "collecting", "diagnosing", "awaiting_approval", "executing"]);

const EVENT_TONE = {
  recovered: "is-good",
  "remediation executed": "is-good",
  "handling finished": "is-good",
  "not resolved": "is-bad",
  "remediation failed": "is-bad",
  "handling crashed": "is-bad",
  "remediation rejected": "is-bad",
  "remediation rejected by policy": "is-bad",
  "approval expired": "is-bad",
  "awaiting approval": "is-active",
  "executing remediation": "is-active",
};

function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined && content !== null) node.textContent = String(content);
  return node;
}

function statusLabel(incident) {
  return t.status[incident.status] ?? incident.status;
}

function relativeTime(iso) {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return t.ago.seconds(Math.round(seconds));
  if (seconds < 3600) return t.ago.minutes(Math.round(seconds / 60));
  if (seconds < 86400) return t.ago.hours(Math.round(seconds / 3600));
  return new Date(iso).toLocaleDateString(language === "zh" ? "zh-CN" : "en");
}

function offsetFrom(start, at) {
  const seconds = Math.max(0, (new Date(at) - new Date(start)) / 1000);
  return seconds < 60 ? `+${Math.round(seconds)}s` : `+${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

/* ---------- incident list ---------- */

function renderList() {
  const all = [...incidents.values()].sort((a, b) => b.opened_at.localeCompare(a.opened_at));
  emptyEl.hidden = all.length > 0;
  countEl.textContent = all.length || "";
  listEl.replaceChildren();

  for (const incident of all) {
    const tone = STATUS_TONE[incident.status] ?? "muted";
    const item = el("li", "incident");
    item.setAttribute("aria-selected", String(incident.id === selectedId));
    item.appendChild(el("span", `dot dot-${tone}${LIVE_STATUSES.has(incident.status) ? " is-live" : ""}`));

    const body = el("div");
    body.appendChild(el("div", "incident-title", incident.alertname));
    const meta = el("div", "incident-meta");
    meta.append(
      el("span", null, incident.hostname ?? t.unknownHost),
      el("span", null, "·"),
      el("span", null, statusLabel(incident)),
      el("span", null, "·"),
      el("span", null, relativeTime(incident.opened_at)),
    );
    body.appendChild(meta);
    item.appendChild(body);

    item.addEventListener("click", () => {
      selectedId = incident.id;
      renderList();
      renderDetail();
    });
    listEl.appendChild(item);
  }
}

/* ---------- sparkline ---------- */

const SVG_NS = "http://www.w3.org/2000/svg";

function svg(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  return node;
}

function sparkline(samples, { threshold = 80, width = 320, height = 48 } = {}) {
  const values = samples.map((s) => s.value);
  const top = Math.max(threshold * 1.05, ...values);
  const x = (i) => (i / Math.max(1, values.length - 1)) * width;
  const y = (v) => height - (v / top) * height;

  const chart = svg("svg", { viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "none", role: "img" });
  chart.appendChild(svg("title", {})).textContent = `${t.cpuUsage}: ${values.at(-1).toFixed(1)}%`;

  const defs = svg("defs", {});
  const gradient = svg("linearGradient", { id: "spark-fade", x1: "0", y1: "0", x2: "0", y2: "1" });
  gradient.append(
    svg("stop", { offset: "0%", "stop-color": "var(--accent)", "stop-opacity": "0.25" }),
    svg("stop", { offset: "100%", "stop-color": "var(--accent)", "stop-opacity": "0" }),
  );
  defs.appendChild(gradient);
  chart.appendChild(defs);

  const line = values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  chart.appendChild(svg("path", { class: "spark-area", d: `${line} L${width},${height} L0,${height} Z` }));
  chart.appendChild(svg("line", { class: "spark-threshold", x1: 0, x2: width, y1: y(threshold), y2: y(threshold) }));
  chart.appendChild(svg("path", { class: "spark-line", d: line }));
  chart.appendChild(svg("circle", { class: "spark-end", cx: x(values.length - 1), cy: y(values.at(-1)), r: 4 }));

  const figure = el("div", "spark");
  const head = el("div", "spark-head");
  head.append(el("span", null, t.cpuUsage), el("span", null, t.threshold(threshold)));
  figure.append(head, chart);
  return figure;
}

function cpuSamples(evidence) {
  const probe = evidence?.find((item) => item.probe === "cpu_usage_trend" && item.result?.series?.length);
  return probe?.result.series[0]?.samples ?? null;
}

/* ---------- diagnosis ---------- */

function renderDiagnosis(incident) {
  const diagnosis = incident.diagnosis;
  const card = el("div", "card");
  card.append(
    el("div", "card-label", t.rootCause),
    el("p", "headline", diagnosis.root_cause),
    el("p", "body-text", diagnosis.summary),
  );

  const chips = el("div", "chips");
  chips.appendChild(
    el("span", `pill pill-${diagnosis.verified ? "good" : "bad"}`, diagnosis.verified ? t.verified : t.unverified),
  );
  if (diagnosis.culprit_process) {
    const p = diagnosis.culprit_process;
    chips.appendChild(el("span", "pill pill-plain", `${p.name}${p.pid ? ` · pid ${p.pid}` : ""}`));
  }
  if (diagnosis.latency_ms) {
    chips.appendChild(el("span", "pill pill-muted", `${(diagnosis.latency_ms / 1000).toFixed(1)}s`));
  }
  if (diagnosis.evidence_used?.length) {
    chips.appendChild(el("span", "pill pill-muted", t.probesCited(diagnosis.evidence_used.length)));
  }
  card.appendChild(chips);

  const meter = el("div", "meter");
  const track = el("div", "meter-track");
  const fill = el("div", `meter-fill${diagnosis.confidence < 0.6 ? " is-low" : ""}`);
  fill.style.width = `${Math.round(diagnosis.confidence * 100)}%`;
  track.appendChild(fill);
  meter.append(el("span", null, t.confidence), track, el("span", null, diagnosis.confidence.toFixed(2)));
  card.appendChild(meter);

  if (diagnosis.verification_note) card.appendChild(el("p", "body-text", diagnosis.verification_note));

  const samples = cpuSamples(incident.evidence);
  if (samples?.length > 1) card.appendChild(sparkline(samples));
  return card;
}

/* ---------- approval ---------- */

async function decide(incidentId, decision, actionIndex, button) {
  for (const btn of button.parentElement.querySelectorAll("button")) btn.disabled = true;
  await fetch(`/api/incidents/${incidentId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, action_index: actionIndex }),
  });
}

function renderApproval(incident) {
  const approval = incident.approval;
  const expired = new Date(approval.expires_at) <= new Date();
  const pending = incident.status === "awaiting_approval" && !expired;
  const nodes = [
    el("h3", null, pending ? t.actionRequired : expired ? t.approvalExpired : t.proposedRemediation),
  ];

  for (const proposed of approval.actions) {
    const card = el("div", `card action-card${pending ? "" : " is-expired"}`);
    card.append(
      el("div", "card-label", t.actions[proposed.action.action] ?? proposed.action.action),
      el("p", "body-text", proposed.action.reason),
    );
    if (proposed.command) card.appendChild(el("div", "command mono", proposed.command));

    const chips = el("div", "chips");
    const tone = proposed.risk === "forbidden" ? "bad" : proposed.risk === "dangerous" ? "warn" : "muted";
    chips.appendChild(el("span", `pill pill-${tone}`, t.riskAction(t.risks[proposed.risk] ?? proposed.risk)));
    if (proposed.blocked_reason) chips.appendChild(el("span", "pill pill-muted", proposed.blocked_reason));
    if (expired && proposed.executable) chips.appendChild(el("span", "pill pill-muted", t.runYourself));
    card.appendChild(chips);

    if (pending && proposed.executable) {
      const buttons = el("div", "buttons");
      const approve = el("button", "btn btn-primary", t.approve);
      approve.addEventListener("click", () => decide(incident.id, "approve", proposed.index, approve));
      const reject = el("button", "btn btn-ghost", t.reject);
      reject.addEventListener("click", () => decide(incident.id, "reject", proposed.index, reject));
      buttons.append(approve, reject);
      card.appendChild(buttons);
    }
    nodes.push(card);
  }
  return nodes;
}

/* ---------- outcome, timeline, evidence ---------- */

function renderOutcome(incident) {
  const last = [...incident.timeline].reverse().find((e) => e.event === "recovered" || e.event === "not resolved");
  if (!last) return null;
  const good = last.event === "recovered";
  const banner = el("div", `banner banner-${good ? "good" : "bad"}`);
  banner.appendChild(el("span", "banner-icon", good ? "✓" : "!"));
  const text = el("div");
  text.append(el("strong", null, `${good ? t.recovered : t.stillFailing} `), el("span", null, last.detail ?? ""));
  banner.appendChild(text);
  return banner;
}

function renderTimeline(incident) {
  const list = el("ul", "timeline");
  for (const entry of incident.timeline) {
    const item = el("li", EVENT_TONE[entry.event] ?? "");
    const head = el("div", "tl-head");
    head.append(
      el("span", "tl-event", t.events[entry.event] ?? entry.event),
      el("span", "tl-offset", offsetFrom(incident.opened_at, entry.at)),
    );
    item.appendChild(head);
    if (entry.detail) item.appendChild(el("div", "tl-detail", entry.detail));
    list.appendChild(item);
  }
  return list;
}

function summarizeSeries(series) {
  return series
    .map((entry) => {
      const host = entry.labels?.hostname ?? entry.labels?.instance ?? "?";
      if (entry.value !== undefined) return `${host}: ${entry.value.toFixed(2)}`;
      const values = (entry.samples ?? []).map((s) => s.value);
      if (!values.length) return `${host}: -`;
      const avg = values.reduce((a, b) => a + b, 0) / values.length;
      return `${host}: ${values.at(-1).toFixed(1)} · max ${Math.max(...values).toFixed(1)} · avg ${avg.toFixed(1)} · n=${values.length}`;
    })
    .join("\n");
}

function renderEvidence(evidence) {
  return evidence.map((item) => {
    const block = el("details", "evidence");
    const summary = el("summary");
    summary.append(el("span", null, item.probe), el("span", "probe-note", item.error ? t.probeFailed : t.probeOk));
    block.appendChild(summary);

    if (item.error) {
      block.appendChild(el("p", "body-text", item.error));
    } else if (item.result?.output !== undefined) {
      block.append(
        el("div", "query mono", `$ ${item.result.command}`),
        el("pre", null, item.result.output || t.noOutput),
      );
    } else if (item.result?.series) {
      block.append(el("div", "query mono", item.result.query), el("pre", null, summarizeSeries(item.result.series)));
    } else {
      block.appendChild(el("pre", null, JSON.stringify(item.result, null, 2)));
    }
    return block;
  });
}

/* ---------- detail ---------- */

function renderDetail() {
  const incident = incidents.get(selectedId);
  if (!incident) {
    detailEl.replaceChildren(el("p", "placeholder", t.selectIncident));
    return;
  }

  const head = el("div", "detail-head");
  head.append(
    el("h1", "detail-title", `${incident.alertname} · ${incident.hostname ?? t.unknownHost}`),
    el("p", "detail-sub", incident.summary),
  );
  const chips = el("div", "detail-chips");
  chips.appendChild(el("span", `pill pill-${STATUS_TONE[incident.status] ?? "muted"}`, statusLabel(incident)));
  if (incident.intent) chips.appendChild(el("span", "pill pill-muted", incident.intent));
  chips.appendChild(el("span", "pill pill-muted", t.openedAgo(relativeTime(incident.opened_at))));
  head.appendChild(chips);

  const body = el("div");
  const outcome = renderOutcome(incident);
  if (outcome) {
    const block = el("div", "block");
    block.appendChild(outcome);
    body.appendChild(block);
  }
  if (incident.approval?.actions?.length) {
    const block = el("div", "block");
    block.append(...renderApproval(incident));
    body.appendChild(block);
  }
  if (incident.diagnosis) {
    const block = el("div", "block");
    block.append(el("h3", null, t.diagnosis), renderDiagnosis(incident));
    body.appendChild(block);
  }

  const timelineBlock = el("div", "block");
  timelineBlock.append(el("h3", null, t.timeline), renderTimeline(incident));
  body.appendChild(timelineBlock);

  if (incident.evidence?.length) {
    const block = el("div", "block");
    block.append(el("h3", null, t.evidence), ...renderEvidence(incident.evidence));
    body.appendChild(block);
  }

  detailEl.replaceChildren(head, body);
}

/* ---------- theme and language ---------- */

function currentTheme() {
  return (
    document.documentElement.dataset.theme ??
    (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
  );
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("theme", theme);
  themeButton.textContent = theme === "dark" ? "☀ Light" : "☾ Dark";
  themeButton.setAttribute("aria-label", `${t.theme}: ${theme}`);
}

function applyLanguage(next) {
  language = next;
  t = dict(language);
  localStorage.setItem("language", language);
  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";

  languageButton.textContent = LANGUAGE_LABEL[LANGUAGES[(LANGUAGES.indexOf(language) + 1) % LANGUAGES.length]];
  languageButton.setAttribute("aria-label", t.language);
  document.getElementById("rail-title").textContent = t.incidents;
  document.getElementById("empty-title").textContent = t.emptyTitle;
  document.getElementById("empty-hint").textContent = t.emptyHint;
  applyTheme(currentTheme());
  renderList();
  renderDetail();
}

themeButton.addEventListener("click", () => applyTheme(currentTheme() === "dark" ? "light" : "dark"));
languageButton.addEventListener("click", () =>
  applyLanguage(LANGUAGES[(LANGUAGES.indexOf(language) + 1) % LANGUAGES.length]),
);

/* ---------- live updates ---------- */

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
    connectionEl.textContent = t.live;
    connectionEl.className = "pill pill-good";
  };
  source.onmessage = (message) => upsert(JSON.parse(message.data));
  source.onerror = () => {
    connectionEl.textContent = t.reconnecting;
    connectionEl.className = "pill pill-bad";
  };
}

applyLanguage(language);
connectionEl.textContent = t.connecting;
loadInitial().then(connect);
setInterval(renderList, 30_000); // keep the relative timestamps honest
