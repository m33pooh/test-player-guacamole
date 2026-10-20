// SpiritVale Bot Web Dashboard Telemetry Engine

const STATE_DESCRIPTIONS = {
    "IDLE": "Waiting for bot session to start",
    "TOWN_REFILL": "Refilling HP & Potions at Heart NPC near town fountain",
    "TOWN_OPEN_MAP": "Interacting with Teleport Crystal to open World Map",
    "TOWN_WARP": "Selecting Stormreef Isle (Lv 61-65) and warping",
    "FIELD_COMBAT": "Active Combat combo execution on monster cluster",
    "FIELD_NAVIGATE": "Tracking nearest monster red dot on Minimap",
    "DEAD_RECOVERY": "Clicking Respawn In Town and waiting for town load"
};

let lastActionId = 0;
let lastHistoryId = 0;

// DOM Elements
const kpiUptime = document.getElementById("kpi-uptime");
const kpiMobs = document.getElementById("kpi-mobs");
const kpiWarps = document.getElementById("kpi-warps");
const kpiRecoveries = document.getElementById("kpi-recoveries");
const systemStatusText = document.getElementById("system-status-text");
const systemStatusBadge = document.getElementById("system-status-badge");

const liveStreamImg = document.getElementById("live-stream-img");
const toggleStream = document.getElementById("toggle-stream");
const btnForceRefresh = document.getElementById("btn-force-refresh");
const hudLocation = document.getElementById("hud-location");
const currentActionText = document.getElementById("current-action-text");
const telemetryTimestamp = document.getElementById("telemetry-timestamp");

const workflowStateText = document.getElementById("workflow-state-text");
const workflowStateDesc = document.getElementById("workflow-state-desc");
const hpPercentText = document.getElementById("hp-percent-text");
const hpBarFill = document.getElementById("hp-bar-fill");
const hpStatusText = document.getElementById("hp-status-text");
const hpRatioRaw = document.getElementById("hp-ratio-raw");

const valMonstersCount = document.getElementById("val-monsters-count");
const valMonstersSub = document.getElementById("val-monsters-sub");
const valTargetCoords = document.getElementById("val-target-coords");
const valTargetMode = document.getElementById("val-target-mode");
const valLocationType = document.getElementById("val-location-type");
const valSafezone = document.getElementById("val-safezone");
const radarTargetsList = document.getElementById("radar-targets-list");

const actionLogStream = document.getElementById("action-log-stream");
const actionCount = document.getElementById("action-count");
const historyStrip = document.getElementById("history-strip");
const historyCount = document.getElementById("history-count");

const snapshotModal = document.getElementById("snapshot-modal");
const modalCloseBtn = document.getElementById("modal-close-btn");
const modalSnapshotTitle = document.getElementById("modal-snapshot-title");
const modalSnapshotBody = document.getElementById("modal-snapshot-body");

function formatSeconds(secs) {
    const hrs = Math.floor(secs / 3600);
    const mins = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

// Fetch Telemetry Data
async function fetchTelemetry() {
    try {
        const response = await fetch("/api/telemetry");
        if (!response.ok) throw new Error("Offline");
        const data = await response.json();

        // System status
        systemStatusBadge.style.color = "var(--neon-green)";
        systemStatusBadge.style.borderColor = "rgba(0, 255, 136, 0.4)";
        systemStatusText.innerText = "ONLINE - " + data.state;

        // KPIs
        if (data.stats) {
            kpiUptime.innerText = formatSeconds(data.stats.uptime_seconds || 0);
            kpiMobs.innerText = data.stats.monsters_engaged || 0;
            kpiWarps.innerText = data.stats.warps_executed || 0;
            kpiRecoveries.innerText = data.stats.deaths_recovered || 0;
        }

        // State card
        workflowStateText.innerText = data.state;
        workflowStateDesc.innerText = STATE_DESCRIPTIONS[data.state] || "Active bot operations";

        // HP Bar
        const hpPercent = data.hp_percent;
        hpPercentText.innerText = `${hpPercent}%`;
        hpBarFill.style.width = `${Math.max(4, hpPercent)}%`;
        hpRatioRaw.innerText = `Ratio: ${data.hp_ratio.toFixed(3)}`;

        if (hpPercent < 35) {
            hpBarFill.classList.add("danger");
            hpStatusText.innerText = "Status: Critical (Auto Potion)";
            hpPercentText.style.color = "var(--neon-red)";
        } else {
            hpBarFill.classList.remove("danger");
            hpStatusText.innerText = "Status: Healthy";
            hpPercentText.style.color = "var(--neon-green)";
        }

        // Target & Monster Info
        valMonstersCount.innerText = data.monsters_count;
        valMonstersSub.innerText = data.monsters_count > 0 ? `${data.monsters_count} HP bars on screen` : "Radar clear";

        if (data.current_target) {
            valTargetCoords.innerText = `(${data.current_target.x}, ${data.current_target.y})`;
            valTargetMode.innerText = `Mode: ${data.current_target.type || 'locked'}`;
        } else {
            valTargetCoords.innerText = "None";
            valTargetMode.innerText = "Mode: search";
        }

        // Location & Zone
        if (data.in_town) {
            valLocationType.innerText = "TOWN";
            valLocationType.className = "mini-value text-cyan";
            valSafezone.innerText = "Safe Zone (No Attack)";
            hudLocation.innerText = "ZONE: TOWN FOUNTAIN";
        } else {
            valLocationType.innerText = "FIELD";
            valLocationType.className = "mini-value text-red";
            valSafezone.innerText = "Hunting Ground (Active Combat)";
            hudLocation.innerText = "ZONE: STORMREEF ISLE";
        }

        // Current Action
        currentActionText.innerText = data.current_action || "Idle";
        telemetryTimestamp.innerText = data.timestamp || "00:00:00";

        // Radar list
        if (data.monsters && data.monsters.length > 0) {
            radarTargetsList.innerHTML = data.monsters.map((m, idx) => `
                <div class="radar-item">
                    <span>Target #${idx + 1}</span>
                    <span class="text-red">(${m[0]}, ${m[1]})</span>
                </div>
            `).join("");
        } else {
            radarTargetsList.innerHTML = `<div class="radar-empty">No active monster HP bars detected</div>`;
        }

    } catch (err) {
        systemStatusBadge.style.color = "var(--neon-amber)";
        systemStatusText.innerText = "CONNECTING...";
    }
}

// Fetch Action Logs
async function fetchActions() {
    try {
        const response = await fetch("/api/actions");
        if (!response.ok) return;
        const actions = await response.json();

        actionCount.innerText = `${actions.length} events`;

        if (actions.length > 0 && actions[0].id !== lastActionId) {
            lastActionId = actions[0].id;
            actionLogStream.innerHTML = actions.map(act => {
                let catClass = "combat";
                if (act.description.includes("Town") || act.description.includes("Heart")) catClass = "town";
                else if (act.description.includes("Warp") || act.description.includes("Map")) catClass = "warp";
                else if (act.description.includes("Death") || act.description.includes("Respawn")) catClass = "death";

                return `
                    <div class="log-row ${catClass}">
                        <span class="log-time">${act.timestamp}</span>
                        <span class="log-state-tag">${act.state}</span>
                        <span class="log-message">${act.description}</span>
                    </div>
                `;
            }).join("");
        }
    } catch (err) {
        // Ignore fetch errors
    }
}

// Fetch Scan Snapshots
async function fetchHistory() {
    try {
        const response = await fetch("/api/history");
        if (!response.ok) return;
        const history = await response.json();

        historyCount.innerText = `${history.length} scans`;

        if (history.length > 0 && history[0].id !== lastHistoryId) {
            lastHistoryId = history[0].id;
            historyStrip.innerHTML = history.map(item => `
                <div class="history-card" onclick="openSnapshotModal(${item.id})">
                    <img class="history-thumb" src="data:image/jpeg;base64,${item.thumb_b64}" alt="Scan #${item.id}">
                    <span class="history-time">${item.timestamp}</span>
                    <span class="history-state">${item.state}</span>
                </div>
            `).join("");
        }
    } catch (err) {
        // Ignore fetch errors
    }
}

// Modal Inspector
window.openSnapshotModal = async function(id) {
    try {
        const response = await fetch("/api/history");
        const history = await response.json();
        const item = history.find(h => h.id === id);
        if (!item) return;

        modalSnapshotTitle.innerText = `Scan Snapshot #${item.id} - ${item.timestamp}`;
        modalSnapshotBody.innerHTML = `
            <div style="text-align: center;">
                <img src="data:image/jpeg;base64,${item.thumb_b64}" style="max-width: 100%; border-radius: 8px; border: 1px solid var(--border-color);" alt="Snapshot">
            </div>
            <div style="background: rgba(0,0,0,0.3); padding: 14px; border-radius: 8px;">
                <div style="font-family: var(--font-mono); font-size: 0.85rem; margin-bottom: 6px;">
                    <strong>State:</strong> <span style="color: var(--neon-cyan);">${item.state}</span>
                </div>
                <div style="font-family: var(--font-mono); font-size: 0.85rem; margin-bottom: 6px;">
                    <strong>Action:</strong> <span>${item.action}</span>
                </div>
                <div style="font-family: var(--font-mono); font-size: 0.85rem;">
                    <strong>Detections:</strong> 
                    <pre style="background: #000; padding: 8px; margin-top: 6px; border-radius: 4px; font-size: 0.78rem; overflow-x: auto;">${JSON.stringify(item.detections, null, 2)}</pre>
                </div>
            </div>
        `;
        snapshotModal.classList.add("open");
    } catch (err) {
        console.error(err);
    }
};

modalCloseBtn.addEventListener("click", () => {
    snapshotModal.classList.remove("open");
});

snapshotModal.addEventListener("click", (e) => {
    if (e.target === snapshotModal) snapshotModal.classList.remove("open");
});

// Force Refresh Snapshot
btnForceRefresh.addEventListener("click", () => {
    liveStreamImg.src = "/api/latest_frame.jpg?t=" + new Date().getTime();
});

// Stream Toggle
toggleStream.addEventListener("change", (e) => {
    if (e.target.checked) {
        liveStreamImg.src = "/api/stream";
    } else {
        liveStreamImg.src = "/api/latest_frame.jpg";
    }
});

// Start Real-time Loops
setInterval(fetchTelemetry, 150);
setInterval(fetchActions, 400);
setInterval(fetchHistory, 1000);
fetchTelemetry();
fetchActions();
fetchHistory();
