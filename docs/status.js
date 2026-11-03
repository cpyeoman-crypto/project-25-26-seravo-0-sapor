/* Only this strict schema may reach the public view. */
(function () {
  "use strict";
  function exactKeys(value, required, optional) {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid row");
    if (required.some(key => !(key in value)) ||
        Object.keys(value).some(key => !required.includes(key) && !optional.includes(key))) {
      throw new Error("Unexpected public fields");
    }
  }
  const EVENT_KINDS = ["connect", "disconnect", "node-online", "node-offline", "uplink-drop",
    "uplink-restore", "new-device", "healing", "watch", "report", "alert", "recovered", "pulse", "test"];
  const FAKE_IP = /^(?:192\.0\.2|198\.51\.100|203\.0\.113)\./;
  const IPV6ISH = /\b[0-9A-Fa-f]{1,4}(?::{1,2}[0-9A-Fa-f]{1,4}){3,}\b/g;
  function maskedText(value, max, singleLine) {
    if (typeof value !== "string" || [...value].length > max) return false;
    if (singleLine && /[\r\n]/.test(value)) return false;
    if (/farm/i.test(value)) return false;
    for (const ip of value.match(/\b\d{1,3}(?:\.\d{1,3}){3}\b/g) || []) {
      if (!FAKE_IP.test(ip)) return false;
    }
    for (const mac of value.match(/\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b/g) || []) {
      if (!mac.toLowerCase().startsWith("02:00:00")) return false;
    }
    for (const six of value.match(IPV6ISH) || []) {
      const lowered = six.toLowerCase();
      if (!lowered.startsWith("02:00:00") && !lowered.startsWith("2001:db8")) return false;
    }
    return true;
  }
  function validate(value) {
    exactKeys(value, ["schema_version", "nodes", "incidents"], ["events"]);
    if (value.schema_version !== 1 || !Array.isArray(value.nodes) ||
        !Array.isArray(value.incidents) || value.nodes.length > 200 || value.incidents.length > 200) {
      throw new Error("Unsupported public snapshot");
    }
    for (const row of value.nodes) {
      exactKeys(row, ["alias", "status"], ["cpu_pct", "ram_pct", "disk_pct"]);
      if (!/^client-[a-f0-9]{20}$/.test(row.alias) ||
          !["online", "offline", "blocked", "unknown"].includes(row.status)) throw new Error("Invalid client");
      for (const key of ["cpu_pct", "ram_pct", "disk_pct"]) {
        if (key in row && (!Number.isFinite(row[key]) || row[key] < 0 || row[key] > 100)) {
          throw new Error("Invalid metric");
        }
      }
    }
    for (const row of value.incidents) {
      exactKeys(row, ["alias", "status", "priority"], []);
      if (!/^incident-[a-f0-9]{20}$/.test(row.alias) ||
          !["pending_review", "resolved", "acknowledged"].includes(row.status) ||
          !Number.isInteger(row.priority) || row.priority < 1 || row.priority > 5) {
        throw new Error("Invalid incident");
      }
    }
    if ("events" in value) {
      if (!Array.isArray(value.events) || value.events.length > 50) throw new Error("Unsupported public feed");
      for (const row of value.events) {
        exactKeys(row, ["role", "kind", "title", "message", "priority", "age_min"], []);
        if (!/^[a-z0-9][a-z0-9 -]{0,31}$/.test(row.role) || !EVENT_KINDS.includes(row.kind) ||
            !maskedText(row.title, 160, true) || row.title.length < 1 ||
            !maskedText(row.message, 1500, false) ||
            !Number.isInteger(row.priority) || row.priority < 1 || row.priority > 5 ||
            !Number.isInteger(row.age_min) || row.age_min < 0 || row.age_min > 10080) {
          throw new Error("Invalid event");
        }
      }
    }
    return value;
  }
  if (typeof module !== "undefined") module.exports = { validate };
  if (typeof document === "undefined") return;
  let busy = false;
  const PRIORITY_WORDS = {5: "urgent", 4: "important", 3: "routine", 2: "minor", 1: "minor"};
  function renderIncidents(rows) {
    const section = document.getElementById("incidents");
    if (!rows.length) {
      const ok = document.createElement("article");
      ok.className = "resolved";
      const h = document.createElement("h3");
      h.textContent = "✅ Nothing waiting for review";
      const p = document.createElement("p");
      p.textContent = "The watcher has no open items for the operator right now.";
      ok.append(h, p);
      section.replaceChildren(ok);
      return;
    }
    const counts = {};
    for (const row of rows) counts[row.priority] = (counts[row.priority] || 0) + 1;
    const card = document.createElement("article");
    card.className = "pending_review";
    const h = document.createElement("h3");
    h.textContent = `📬 ${rows.length} thing${rows.length === 1 ? "" : "s"} waiting for the operator to review`;
    const p = document.createElement("p");
    p.textContent = Object.keys(counts).sort((a, b) => b - a)
      .map(k => `${counts[k]} ${PRIORITY_WORDS[k] || "routine"}`).join(" · ");
    const note = document.createElement("p");
    note.className = "meta";
    note.textContent = "These are flagged notifications a human still needs to look at. " +
      "Details stay private; only the count and urgency are published.";
    card.append(h, p, note);
    section.replaceChildren(card);
  }
  function render(id, rows) {
    const section = document.getElementById(id);
    section.replaceChildren(...rows.map(row => {
      const card = document.createElement("article");
      card.className = row.status;
      const heading = document.createElement("h3");
      heading.textContent = row.alias;
      const detail = document.createElement("p");
      detail.textContent = row.status.replaceAll("_", " ") +
        (row.priority ? ` - priority ${row.priority}` : "");
      card.append(heading, detail);
      for (const [key, label] of [["cpu_pct", "CPU"], ["ram_pct", "RAM"], ["disk_pct", "Disk"]]) {
        if (key in row) {
          const metric = document.createElement("p");
          metric.textContent = `${label}: ${row[key]}%`;
          card.append(metric);
        }
      }
      return card;
    }));
  }
  function age(minutes) {
    if (minutes < 60) return `${minutes} min ago`;
    if (minutes < 1440) return `${Math.floor(minutes / 60)} h ago`;
    return `${Math.floor(minutes / 1440)} d ago`;
  }
  function renderEvents(rows) {
    const section = document.getElementById("events");
    if (!rows.length) {
      const empty = document.createElement("p");
      empty.textContent = "No masked notifications in the published window.";
      section.replaceChildren(empty);
      return;
    }
    section.replaceChildren(...rows.map(row => {
      const card = document.createElement("article");
      card.className = `event p${row.priority}`;
      const heading = document.createElement("h3");
      heading.textContent = row.title;
      const meta = document.createElement("p");
      meta.className = "meta";
      meta.textContent = `${row.role} · priority ${row.priority} · ${age(row.age_min)} at snapshot time`;
      card.append(heading, meta);
      if (row.message) {
        const body = document.createElement("div");
        body.className = "body";
        body.textContent = row.message;
        card.append(body);
      }
      return card;
    }));
  }
  async function refresh() {
    if (busy) return;
    busy = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(`status.json?t=${Date.now()}`, {cache:"no-store", signal:controller.signal});
      if (!response.ok) throw new Error("Public snapshot unavailable");
      const value = validate(await response.json());
      renderEvents(value.events || []);
      renderIncidents(value.incidents);
      document.getElementById("state").textContent =
        `Snapshot fetched ${new Date().toLocaleTimeString()}. Source freshness is not verified.`;
    } catch {
      document.getElementById("state").textContent = "Refresh failed - retained snapshot is unverified.";
    } finally {
      clearTimeout(timeout);
      busy = false;
    }
  }
  document.getElementById("refresh").addEventListener("click", refresh);
  refresh();
  setInterval(refresh, 60000);
}());
