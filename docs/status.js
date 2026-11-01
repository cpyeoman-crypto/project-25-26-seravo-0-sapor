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
  function validate(value) {
    exactKeys(value, ["schema_version", "nodes", "incidents"], []);
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
    return value;
  }
  if (typeof module !== "undefined") module.exports = { validate };
  if (typeof document === "undefined") return;
  let busy = false;
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
  async function refresh() {
    if (busy) return;
    busy = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(`status.json?t=${Date.now()}`, {cache:"no-store", signal:controller.signal});
      if (!response.ok) throw new Error("Public snapshot unavailable");
      const value = validate(await response.json());
      render("nodes", value.nodes);
      render("incidents", value.incidents);
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
