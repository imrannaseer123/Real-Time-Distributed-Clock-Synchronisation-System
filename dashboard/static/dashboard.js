/**
 * dashboard.js – Real-time dashboard logic
 * ════════════════════════════════════════
 * • Polls /api/state every 2 s → updates hero cards + client table.
 * • Polls /api/history every 5 s → updates three Chart.js charts.
 * • Handles "server offline" state gracefully.
 */

"use strict";

// ─── DOM refs ──────────────────────────────────────────────────────────────
const srvTimeEl    = document.getElementById("srv-time");
const srvUnixEl    = document.getElementById("srv-unix");
const clientCountEl= document.getElementById("client-count");
const avgDriftEl   = document.getElementById("avg-drift");
const lastSyncEl   = document.getElementById("last-sync");
const clientTbody  = document.getElementById("client-tbody");
const logTbody     = document.getElementById("log-tbody");
const logCountEl   = document.getElementById("log-count");
const connDot      = document.getElementById("conn-dot");
const connLabel    = document.getElementById("conn-label");
const algoBadge    = document.getElementById("algo-badge");
const btnRefresh   = document.getElementById("btn-refresh");

// ─── Colour palette for per-client chart series ────────────────────────────
const CLIENT_COLOURS = [
  "#38e8ff", "#a78bfa", "#4ade80", "#fbbf24", "#f87171",
  "#60a5fa", "#fb923c", "#e879f9",
];

// ─── Chart.js global defaults ───────────────────────────────────────────────
Chart.defaults.color         = "#8b95b5";
Chart.defaults.font.family   = "'Inter', sans-serif";
Chart.defaults.font.size     = 11;
Chart.defaults.borderColor   = "rgba(255,255,255,0.06)";

function makeChart(id, label, colour) {
  const ctx = document.getElementById(id).getContext("2d");
  return new Chart(ctx, {
    type: "line",
    data: {
      labels:   [],
      datasets: [{
        label,
        data:           [],
        borderColor:    colour,
        backgroundColor: colour + "20",
        borderWidth:    2,
        pointRadius:    3,
        pointHoverRadius: 5,
        tension:        0.35,
        fill:           true,
      }],
    },
    options: {
      animation:   { duration: 400 },
      responsive:  true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#10131e",
          borderColor:     "rgba(255,255,255,0.1)",
          borderWidth:     1,
          padding:         10,
        },
      },
      scales: {
        x: {
          grid:  { color: "rgba(255,255,255,0.04)" },
          ticks: { maxTicksLimit: 8, maxRotation: 0 },
        },
        y: {
          grid:  { color: "rgba(255,255,255,0.04)" },
          ticks: { maxTicksLimit: 6 },
        },
      },
    },
  });
}

function makeMultiChart(id) {
  const ctx = document.getElementById(id).getContext("2d");
  return new Chart(ctx, {
    type: "line",
    data: { labels: [], datasets: [] },
    options: {
      animation:   { duration: 400 },
      responsive:  true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          display:  true,
          position: "top",
          labels:   { color: "#8b95b5", boxWidth: 12, padding: 16 },
        },
        tooltip: {
          backgroundColor: "#10131e",
          borderColor:     "rgba(255,255,255,0.1)",
          borderWidth:     1,
          padding:         10,
        },
      },
      scales: {
        x: { grid: { color: "rgba(255,255,255,0.04)" }, ticks: { maxTicksLimit: 8, maxRotation: 0 } },
        y: { grid: { color: "rgba(255,255,255,0.04)" }, ticks: { maxTicksLimit: 6 } },
      },
    },
  });
}

const offsetChart = makeChart("chart-offset", "Offset (ms)", "#38e8ff");
const rttChart    = makeChart("chart-rtt",    "RTT (ms)",    "#a78bfa");
const driftChart  = makeMultiChart("chart-drift");

// ─── Helpers ───────────────────────────────────────────────────────────────

function fmtUtc(unixSec) {
  if (!unixSec) return "—";
  return new Date(unixSec * 1000).toISOString().replace("T", " ").slice(0, 23) + " UTC";
}

function fmtTime(unixSec) {
  if (!unixSec) return "—";
  return new Date(unixSec * 1000).toISOString().replace("T", " ").slice(11, 23);
}

function setConnected(ok) {
  connDot.className   = "status-dot " + (ok ? "dot-green" : "dot-red");
  connLabel.textContent = ok ? "Connected" : "Server offline";
}

function driftClass(ms) {
  const abs = Math.abs(ms);
  if (abs < 50)  return "pill-green";
  if (abs < 500) return "pill-yellow";
  return "pill-red";
}

function driftMs(client) {
  // drift is stored in seconds in the registry
  const d = parseFloat(client.drift ?? 0);
  return (d * 1000).toFixed(1);
}

const MAX_CHART_POINTS = 40;

// ─── State poll ────────────────────────────────────────────────────────────

async function pollState() {
  try {
    const resp = await fetch("/api/state");
    if (!resp.ok) throw new Error(resp.statusText);
    const data = await resp.json();

    if (data.error) { setConnected(false); return; }
    setConnected(true);

    // ── Hero cards ─────────────────────────────────────────────────────────
    srvTimeEl.textContent  = fmtUtc(data.server_time);
    srvUnixEl.textContent  = "unix: " + (data.server_time ?? "—").toFixed(3);

    const clients = data.clients ?? {};
    const cids    = Object.keys(clients);
    clientCountEl.textContent = cids.length;

    if (cids.length) {
      const drifts  = cids.map(id => parseFloat(clients[id].drift ?? 0));
      const avgDrift = drifts.reduce((a,b) => a+b, 0) / drifts.length;
      avgDriftEl.textContent = (avgDrift * 1000).toFixed(1) + " ms";

      const lastSyncs = cids.map(id => clients[id].last_sync).filter(Boolean);
      if (lastSyncs.length) {
        const latest = lastSyncs.sort().slice(-1)[0];
        lastSyncEl.textContent = latest.split("T")[1].slice(0, 12) + " UTC";
      }

      // ── Algorithm badge ───────────────────────────────────────────────
      const algos     = [...new Set(cids.map(id => clients[id].algorithm).filter(Boolean))];
      const algoLabel = algos.length === 1 ? algos[0].toUpperCase() : "MULTI";
      algoBadge.textContent = algoLabel;
      algoBadge.className   = "badge " + (algoLabel === "BERKELEY" ? "badge-violet" : "badge-cyan");
    }

    // ── Client table ────────────────────────────────────────────────────
    if (!cids.length) {
      clientTbody.innerHTML = `<tr><td colspan="9" class="empty-msg">No clients connected yet…</td></tr>`;
      return;
    }

    clientTbody.innerHTML = cids.map(id => {
      const c   = clients[id];
      const dMs = parseFloat(driftMs(c));
      const cls = driftClass(dMs);
      return `
        <tr>
          <td><code class="mono">${id}</code></td>
          <td><span class="pill ${c.algorithm === 'berkeley' ? 'badge-violet' : 'badge-cyan'}" style="font-size:.68rem">${(c.algorithm ?? "—").toUpperCase()}</span></td>
          <td class="mono">${fmtTime(c.client_time)}</td>
          <td class="mono">${fmtTime(c.server_time)}</td>
          <td><span class="pill ${cls}">${dMs > 0 ? "+" : ""}${dMs} ms</span></td>
          <td class="mono">${parseFloat(c.rtt_ms ?? 0).toFixed(2)} ms</td>
          <td class="mono">${parseFloat(c.offset_ms ?? 0).toFixed(2)} ms</td>
          <td class="mono">${(c.last_sync ?? "—").replace("T", " ").slice(0, 23)}</td>
          <td><span class="pill pill-green">● synced</span></td>
        </tr>`;
    }).join("");

  } catch (e) {
    setConnected(false);
    console.warn("State poll failed:", e.message);
  }
}

// ─── History poll ──────────────────────────────────────────────────────────

async function pollHistory() {
  try {
    const resp = await fetch("/api/history");
    if (!resp.ok) return;
    const rows = await resp.json();
    if (!rows.length) return;

    // ── Log table ─────────────────────────────────────────────────────────
    const recent = rows.slice(-80).reverse();
    logCountEl.textContent = rows.length + " events";
    logTbody.innerHTML = recent.map(r => `
      <tr>
        <td class="mono">${(r.timestamp ?? "").replace("T"," ").slice(0,23)}</td>
        <td>${r.event ?? "—"}</td>
        <td><code class="mono">${r.client_id ?? "—"}</code></td>
        <td>${(r.algorithm ?? "—").toUpperCase()}</td>
        <td class="mono">${parseFloat(r.rtt_ms ?? 0).toFixed(3)}</td>
        <td class="mono">${parseFloat(r.offset_ms ?? 0).toFixed(3)}</td>
        <td class="mono">${parseFloat(r.server_time ?? 0).toFixed(4)}</td>
      </tr>`).join("");

    // ── Offset chart ──────────────────────────────────────────────────────
    const syncRows = rows.filter(r => r.event === "SYNC_REPORT").slice(-MAX_CHART_POINTS);
    offsetChart.data.labels   = syncRows.map(r => r.timestamp ? r.timestamp.slice(11,19) : "");
    offsetChart.data.datasets[0].data = syncRows.map(r => parseFloat(r.offset_ms ?? 0));
    offsetChart.update();

    // ── RTT chart ─────────────────────────────────────────────────────────
    rttChart.data.labels   = syncRows.map(r => r.timestamp ? r.timestamp.slice(11,19) : "");
    rttChart.data.datasets[0].data = syncRows.map(r => parseFloat(r.rtt_ms ?? 0));
    rttChart.update();

    // ── Per-client drift chart (multi-series) ─────────────────────────────
    const clientIds    = [...new Set(rows.map(r => r.client_id).filter(Boolean))];
    const allTimestamps= [...new Set(rows.map(r => r.timestamp).filter(Boolean))].sort().slice(-MAX_CHART_POINTS);

    driftChart.data.labels = allTimestamps.map(t => t.slice(11,19));
    driftChart.data.datasets = clientIds.map((cid, i) => {
      const colour = CLIENT_COLOURS[i % CLIENT_COLOURS.length];
      const byTs   = {};
      rows.filter(r => r.client_id === cid).forEach(r => { byTs[r.timestamp] = parseFloat(r.offset_ms ?? 0); });
      return {
        label:           cid,
        data:            allTimestamps.map(t => byTs[t] ?? null),
        borderColor:     colour,
        backgroundColor: colour + "18",
        borderWidth:     2,
        pointRadius:     2,
        tension:         0.35,
        fill:            false,
        spanGaps:        true,
      };
    });
    driftChart.update();

  } catch (e) {
    console.warn("History poll failed:", e.message);
  }
}

// ─── Polling loops ─────────────────────────────────────────────────────────

pollState();
pollHistory();
setInterval(pollState,   2000);
setInterval(pollHistory, 5000);

// ─── Manual refresh ─────────────────────────────────────────────────────────
btnRefresh.addEventListener("click", () => {
  pollState();
  pollHistory();

  // Brief spin animation on the button
  btnRefresh.style.transform = "rotate(360deg)";
  btnRefresh.style.transition = "transform 0.4s ease";
  setTimeout(() => {
    btnRefresh.style.transform = "";
    btnRefresh.style.transition = "";
  }, 400);
});
