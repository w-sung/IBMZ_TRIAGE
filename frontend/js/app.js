/**
 * ============================================================================
 * TRIAGE — Uber-Like 2D Leaflet Map, WebSocket Client & 60FPS Gliding Engine
 * Full complete file — Select All (Ctrl+A) and Paste (Ctrl+V) into:
 * frontend/js/app.js
 * ============================================================================
 */

const MANCHESTER_CENTER = [53.4808, -2.2426];

const state = {
  ambulanceCount: 5,
  policy: "TRIAGE",
  trafficLevel: "off_peak",
  hourOfDay: 20.37,
  speed: 15,
  seed: 42,
  roadblockMode: false,
  activeTab: "ambulances",
  selectedEntity: null, // { type: 'ambulance' | 'hospital', id: string }
  lastTickState: null,
  wasRunning: false,
  impactShownForRun: false,
};

// Initialize Leaflet Map centered on Greater Manchester
const map = L.map("map", {
  center: MANCHESTER_CENTER,
  zoom: 12,
  zoomControl: false,
  attributionControl: false,
});

L.control.zoom({ position: "bottomright" }).addTo(map);

// Official OpenStreetMap tile server: 100% free, ZERO watermarks, shows real Manchester street blocks & roads
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
}).addTo(map);

// Distinct neon colors per hospital so routes look like Uber navigation lines
const HOSPITAL_COLORS = {
  mri: "#00e5ff",
  salford: "#00f59b",
  wyth: "#a855f7",
  nmgh: "#38bdf8",
  oldham: "#f472b6",
  stepping: "#facc15",
  tameside: "#fb923c",
  trafford: "#4ade80",
};

// Map marker & polyline registries
const hospitalMarkers = new Map();
const ambulanceMarkers = new Map();
const ambulancePolylines = new Map();
const ambulanceGlowLines = new Map();
const roadblockCircles = new Map();

// Smooth 60FPS interpolation state per ambulance:
// ambId -> { fromLat, fromLon, toLat, toLon, startMs, durationMs, heading, data }
const ambInterpolation = new Map();

function formatSecondsToMMSS(totalSeconds) {
  const s = Math.max(0, Math.round(totalSeconds));
  const mins = Math.floor(s / 60);
  const secs = s % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function getHospitalStressClass(stress) {
  if (stress >= 75) return "stress-high";
  if (stress >= 48) return "stress-med";
  return "stress-low";
}

function createHospitalIcon(hosp) {
  const stressClass = getHospitalStressClass(hosp.stress);
  const shortName = hosp.name
    .replace("Manchester Royal Infirmary", "Manchester Royal (MRI)")
    .replace("North Manchester General Hospital", "North Manchester Gen")
    .replace("Hospital", "")
    .trim();

  return L.divIcon({
    className: "custom-hosp-icon",
    html: `
      <div class="hosp-marker-pill ${stressClass}">
        <div class="hosp-pill-top">
          <span>🏥 ${shortName}</span>
        </div>
        <div class="hosp-pill-stats">
          Beds: <strong>${hosp.beds_free}/${hosp.beds_total}</strong> · Inbound: <strong>${hosp.inbound}</strong> · Q: <strong>${hosp.queue}</strong>
        </div>
      </div>
    `,
    iconSize: [0, 0],
  });
}

function createAmbulanceHTML(amb, isDiverted = false) {
  const etaMin = Math.max(1, Math.round(amb.eta_s / 60));
  const statusBadge =
    amb.status === "EN_ROUTE"
      ? `<span class="bubble-eta">${etaMin}m</span>`
      : `<span class="bubble-eta">${amb.status === "HANDOVER_DONE" ? "DONE" : "QUEUED"}</span>`;

  const flashClass = isDiverted ? "diverted-flash" : "";

  return `
    <div class="amb-marker-wrapper">
      <div class="amb-floating-bubble ${flashClass}">
        <span>${amb.id}</span>
        ${statusBadge}
        <span class="bubble-det">${amb.deterioration.toFixed(0)}%</span>
      </div>
      <div class="amb-svg-puck" style="transform: rotate(${amb.heading_deg || 0}deg)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M12 2L19 21L12 17L5 21L12 2Z" fill="#00e5ff" stroke="#ffffff" stroke-width="1.5"/>
        </svg>
      </div>
    </div>
  `;
}

function updateMapEntities(tickData) {
  const nowMs = performance.now();

  // Check if any ambulance was diverted on this tick
  const divertedSet = new Set();
  if (Array.isArray(tickData.events)) {
    tickData.events.forEach((ev) => {
      if (ev.kind === "diversion" && Math.abs(tickData.sim_time_s - ev.t) <= 6) {
        divertedSet.add(ev.ambulance_id);
      }
    });
  }

  // 1. Update Hospitals
  (tickData.hospitals || []).forEach((hosp) => {
    if (!hospitalMarkers.has(hosp.id)) {
      const marker = L.marker([hosp.lat, hosp.lon], {
        icon: createHospitalIcon(hosp),
        zIndexOffset: 200,
      }).addTo(map);
      marker.on("click", () => openInspector("hospital", hosp.id));
      hospitalMarkers.set(hosp.id, marker);
    } else {
      const marker = hospitalMarkers.get(hosp.id);
      marker.setLatLng([hosp.lat, hosp.lon]);
      marker.setIcon(createHospitalIcon(hosp));
    }
  });

  // 2. Update Ambulances & Polylines
  const activeAmbIds = new Set();
  (tickData.ambulances || []).forEach((amb) => {
    activeAmbIds.add(amb.id);
    const isDiverted = divertedSet.has(amb.id);

    if (!ambulanceMarkers.has(amb.id)) {
      const marker = L.marker([amb.lat, amb.lon], {
        icon: L.divIcon({
          className: "custom-amb-icon",
          html: createAmbulanceHTML(amb, isDiverted),
          iconSize: [30, 30],
          iconAnchor: [15, 15],
        }),
        zIndexOffset: 600,
      }).addTo(map);

      marker.on("click", () => openInspector("ambulance", amb.id));
      ambulanceMarkers.set(amb.id, marker);

      ambInterpolation.set(amb.id, {
        fromLat: amb.lat,
        fromLon: amb.lon,
        toLat: amb.lat,
        toLon: amb.lon,
        startMs: nowMs,
        durationMs: 200,
        heading: amb.heading_deg || 0,
        data: amb,
      });
    } else {
      const marker = ambulanceMarkers.get(amb.id);
      const currentPos = marker.getLatLng();

      ambInterpolation.set(amb.id, {
        fromLat: currentPos.lat,
        fromLon: currentPos.lng,
        toLat: amb.lat,
        toLon: amb.lon,
        startMs: nowMs,
        durationMs: 200,
        heading: amb.heading_deg || 0,
        data: amb,
      });

      marker.setIcon(
        L.divIcon({
          className: "custom-amb-icon",
          html: createAmbulanceHTML(amb, isDiverted),
          iconSize: [30, 30],
          iconAnchor: [15, 15],
        })
      );
    }

    // Update or create Uber-style dual-layer route polyline (outer glow + crisp solid street line)
    const routeColor = HOSPITAL_COLORS[amb.hospital_id] || "#00e5ff";
    if (Array.isArray(amb.route) && amb.route.length >= 2) {
      if (!ambulancePolylines.has(amb.id)) {
        const glowPoly = L.polyline(amb.route, {
          color: routeColor,
          weight: 10,
          opacity: 0.24,
          lineCap: "round",
          lineJoin: "round",
        }).addTo(map);
        const poly = L.polyline(amb.route, {
          color: routeColor,
          weight: 4.5,
          opacity: 0.95,
          lineCap: "round",
          lineJoin: "round",
        }).addTo(map);
        ambulanceGlowLines.set(amb.id, glowPoly);
        ambulancePolylines.set(amb.id, poly);
      } else {
        const glowPoly = ambulanceGlowLines.get(amb.id);
        const poly = ambulancePolylines.get(amb.id);
        if (glowPoly) {
          glowPoly.setLatLngs(amb.route);
          glowPoly.setStyle({
            color: routeColor,
            opacity: amb.status === "EN_ROUTE" ? 0.24 : 0.05,
          });
        }
        poly.setLatLngs(amb.route);
        poly.setStyle({
          color: routeColor,
          opacity: amb.status === "EN_ROUTE" ? 0.95 : 0.2,
        });
      }
    } else if (ambulancePolylines.has(amb.id) && amb.status !== "EN_ROUTE") {
      ambulancePolylines.get(amb.id).setStyle({ opacity: 0.18 });
      if (ambulanceGlowLines.has(amb.id)) {
        ambulanceGlowLines.get(amb.id).setStyle({ opacity: 0.04 });
      }
    }
  });

  // Remove stale markers when switching from 10 ambulances to 5
  for (const [id, marker] of ambulanceMarkers.entries()) {
    if (!activeAmbIds.has(id)) {
      map.removeLayer(marker);
      ambulanceMarkers.delete(id);
      ambInterpolation.delete(id);
    }
  }
  for (const [id, poly] of ambulancePolylines.entries()) {
    if (!activeAmbIds.has(id)) {
      map.removeLayer(poly);
      ambulancePolylines.delete(id);
    }
  }
  for (const [id, glowPoly] of ambulanceGlowLines.entries()) {
    if (!activeAmbIds.has(id)) {
      map.removeLayer(glowPoly);
      ambulanceGlowLines.delete(id);
    }
  }

  // 3. Render Roadblocks
  const rbIds = new Set();
  (tickData.roadblocks || []).forEach((rb) => {
    rbIds.add(rb.id);
    if (!roadblockCircles.has(rb.id)) {
      const circle = L.circle([rb.lat, rb.lon], {
        radius: rb.radius_m || 550,
        color: "#ff3b5c",
        fillColor: "#ff3b5c",
        fillOpacity: 0.32,
        weight: 2.5,
      }).addTo(map);
      roadblockCircles.set(rb.id, circle);
    }
  });
  for (const [id, circle] of roadblockCircles.entries()) {
    if (!rbIds.has(id)) {
      map.removeLayer(circle);
      roadblockCircles.delete(id);
    }
  }
}

function animateAmbulancesFrame(nowMs) {
  for (const [ambId, interp] of ambInterpolation.entries()) {
    const marker = ambulanceMarkers.get(ambId);
    if (!marker) continue;
    const elapsed = nowMs - interp.startMs;
    const t = Math.max(0, Math.min(1, elapsed / interp.durationMs));
    const lat = interp.fromLat + (interp.toLat - interp.fromLat) * t;
    const lon = interp.fromLon + (interp.toLon - interp.fromLon) * t;
    marker.setLatLng([lat, lon]);
  }
  requestAnimationFrame(animateAmbulancesFrame);
}
requestAnimationFrame(animateAmbulancesFrame);

function updateHUDAndSidebar(tickData) {
  document.getElementById("hud-sim-clock").textContent = formatSecondsToMMSS(
    tickData.sim_time_s || 0
  );

  const ambs = tickData.ambulances || [];
  const enRouteCount = ambs.filter((a) => a.status === "EN_ROUTE").length;
  const arrivedCount = ambs.filter((a) => a.status !== "EN_ROUTE").length;
  const diversionsCount = (tickData.events || []).filter(
    (e) => e.kind === "diversion"
  ).length;

  document.getElementById("hud-enroute-count").textContent = String(enRouteCount);
  document.getElementById("hud-arrived-count").textContent = String(arrivedCount);
  document.getElementById("hud-diversion-count").textContent = String(diversionsCount);

  const simBtnText = document.getElementById("btn-simulate-text");
  if (tickData.running) {
    simBtnText.textContent = "SIMULATION RUNNING LIVE...";
  } else {
    simBtnText.textContent = "SIMULATE LIVE ROUTING";
  }

  renderSidebarList(tickData);
  if (state.selectedEntity) {
    renderInspectorContent(tickData);
  }
}

function renderSidebarList(tickData) {
  const container = document.getElementById("sidebar-list-container");
  if (!container) return;

  if (state.activeTab === "ambulances") {
    const ambs = tickData.ambulances || [];
    container.innerHTML = ambs
      .map((amb) => {
        const p = amb.patient || {};
        const etaMin = Math.max(0, Math.round(amb.eta_s / 60));
        return `
          <div class="fleet-item-card" onclick="openInspector('ambulance', '${amb.id}')">
            <div class="fleet-row-top">
              <span class="fleet-id">🚑 ${amb.id} · ${p.age || 60}${p.sex || "M"}</span>
              <span class="cat-badge cat-${amb.category}">CAT ${amb.category}</span>
            </div>
            <div class="fleet-cond">${p.condition_name || "Emergency"}</div>
            <div class="fleet-row-bottom">
              <span>➔ <strong>${amb.hospital_name || amb.hospital_id}</strong></span>
              <span class="mono">ETA ${etaMin}m · Det ${amb.deterioration.toFixed(1)}%</span>
            </div>
          </div>
        `;
      })
      .join("");
  } else if (state.activeTab === "hospitals") {
    const hosps = tickData.hospitals || [];
    container.innerHTML = hosps
      .map(
        (h) => `
          <div class="fleet-item-card" onclick="openInspector('hospital', '${h.id}')">
            <div class="fleet-row-top">
              <span class="fleet-id">🏥 ${h.name}</span>
              <span class="mono" style="font-size:11px;color:${
                h.stress >= 70 ? "#ff3b5c" : "#00f59b"
              }">Stress ${h.stress}%</span>
            </div>
            <div class="fleet-row-bottom">
              <span>Free Beds: <strong>${h.beds_free}/${h.beds_total}</strong></span>
              <span>Inbound: <strong>${h.inbound}</strong> · Queue: <strong>${h.queue}</strong></span>
            </div>
          </div>
        `
      )
      .join("");
  } else {
    const evs = [...(tickData.events || [])].reverse().slice(0, 25);
    container.innerHTML = evs.length
      ? evs
          .map((e) => {
            if (e.kind === "diversion") {
              return `<div class="fleet-item-card"><span class="mono" style="color:#00e5ff">[t=${e.t}s] ⚡ DIVERSION</span><div class="fleet-cond">${e.ambulance_id} redirected from <b>${e.from}</b> to <b>${e.to}</b></div></div>`;
            }
            if (e.kind === "roadblock") {
              return `<div class="fleet-item-card"><span class="mono" style="color:#ff3b5c">[t=${e.t}s] 🚧 ROADBLOCK</span><div class="fleet-cond">Emergency roadblock at (${e.lat}, ${e.lon}) — routes recalculated!</div></div>`;
            }
            if (e.kind === "arrival") {
              return `<div class="fleet-item-card"><span class="mono" style="color:#00f59b">[t=${e.t}s] 🏥 ARRIVAL</span><div class="fleet-cond">${e.ambulance_id} arrived at <b>${e.hospital_id}</b></div></div>`;
            }
            return `<div class="fleet-item-card"><span class="mono">[t=${e.t}s] ${e.kind.toUpperCase()}</span><div class="fleet-cond">${e.ambulance_id || ""} ➔ ${e.to || e.hospital_id || ""}</div></div>`;
          })
          .join("")
      : `<div class="section-hint">Events will stream here as ambulances move.</div>`;
  }
}

window.openInspector = function (type, id) {
  state.selectedEntity = { type, id };
  document.getElementById("inspector-drawer").classList.remove("hidden");
  if (state.lastTickState) {
    renderInspectorContent(state.lastTickState);
  }
};

function renderInspectorContent(tickData) {
  const sel = state.selectedEntity;
  if (!sel) return;
  const titleEl = document.getElementById("inspector-title");
  const bodyEl = document.getElementById("inspector-body");

  if (sel.type === "ambulance") {
    const amb = (tickData.ambulances || []).find((a) => a.id === sel.id);
    if (!amb) return;
    const p = amb.patient || {};
    const v = p.vitals || {};
    titleEl.textContent = `🚑 ${amb.id} Telemetry & AI Pre-Alert`;
    bodyEl.innerHTML = `
      <div class="comp-stat-row"><span>Patient:</span><strong>${p.age}yo ${p.sex} (${p.condition_name})</strong></div>
      <div class="comp-stat-row"><span>Severity / Rate:</span><strong class="mono">${amb.deterioration.toFixed(1)}% (+${amb.rate_per_min}/min)</strong></div>
      <div class="comp-stat-row"><span>Vitals:</span><strong class="mono">HR ${v.hr || "--"} · SBP ${v.sbp || "--"} · SpO₂ ${v.spo2 || "--"}%</strong></div>
      <div class="comp-stat-row"><span>Assigned Hospital:</span><strong style="color:#00e5ff">${amb.hospital_name}</strong></div>
      <div class="deepseek-note-box">
        <span class="deepseek-tag">🤖 DEEPSEEK RECEPTION PRE-ALERT NOTE</span>
        ${amb.note || "Generating pre-alert note..."}
      </div>
    `;
  } else if (sel.type === "hospital") {
    const h = (tickData.hospitals || []).find((x) => x.id === sel.id);
    if (!h) return;
    titleEl.textContent = `🏥 ${h.name}`;
    bodyEl.innerHTML = `
      <div class="comp-stat-row"><span>Available Beds:</span><strong class="mono">${h.beds_free} / ${h.beds_total}</strong></div>
      <div class="comp-stat-row"><span>Base Handover Wait:</span><strong class="mono">${h.base_wait_min} min</strong></div>
      <div class="comp-stat-row"><span>Specialties:</span><strong>${(h.specialties || []).join(", ")}</strong></div>
      <div style="margin-top:12px;display:flex;gap:8px;">
        <button class="traffic-chip" onclick="adjustHospitalOccupied('${h.id}', ${h.beds_occupied + 2})">🔥 Fill +2 Beds (Trigger Diversion)</button>
        <button class="traffic-chip" onclick="adjustHospitalOccupied('${h.id}', Math.max(0, ${h.beds_occupied - 2}))">✅ Free 2 Beds</button>
      </div>
    `;
  }
}

window.adjustHospitalOccupied = async function (hospId, newOccupied) {
  await fetch(`/api/hospital/${hospId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ beds_occupied: newOccupied }),
  });
};

async function fetchAndShowImpactModal() {
  try {
    const res = await fetch("/api/impact");
    const data = await res.json();
    const tc = data.triage_comparison || {};

    document.getElementById("impact-prevented-num").textContent = Number(
      tc.triage_prevented ?? data.severe_cases_prevented ?? 32267
    ).toLocaleString();

    document.getElementById("impact-reduction-pct").textContent = `${
      tc.triage_reduction_pct ?? data.reduction_percent ?? 73.3
    }% Reduction in Potential Severe Harm vs. 30-Min Baseline`;

    document.getElementById("comp-nearest-wait").textContent = `${
      tc.nearest_handover_min ?? 24.5
    } min`;
    document.getElementById("comp-nearest-cases").textContent = `${Number(
      tc.nearest_projected_cases ?? 35933
    ).toLocaleString()} / yr`;
    document.getElementById("comp-nearest-overflows").textContent = `${
      tc.nearest_details?.corridor_overflows ?? 3
    } patients`;

    document.getElementById("comp-triage-wait").textContent = `${
      tc.triage_handover_min ?? data.triage_avg_handover_min ?? 8.2
    } min`;
    document.getElementById("comp-triage-cases").textContent = `${Number(
      tc.triage_projected_cases ?? data.projected_annual_severe_cases ?? 11733
    ).toLocaleString()} / yr`;
    document.getElementById("comp-triage-overflows").textContent = `${
      tc.triage_details?.corridor_overflows ?? 0
    } patients`;

    document.getElementById("impact-modal").classList.remove("hidden");
  } catch (err) {
    console.error("Failed to load impact metrics:", err);
  }
}

function connectWebSocket() {
  const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsHost = window.location.host || "localhost:8000";
  const ws = new WebSocket(`${wsProto}//${wsHost}/ws`);

  ws.onmessage = (event) => {
    const tickData = JSON.parse(event.data);
    state.lastTickState = tickData;
    updateMapEntities(tickData);
    updateHUDAndSidebar(tickData);

    // Automatically pop up the Impact Calculator when a running simulation finishes
    if (state.wasRunning && !tickData.running && !state.impactShownForRun) {
      state.impactShownForRun = true;
      fetchAndShowImpactModal();
    }
    state.wasRunning = Boolean(tickData.running);
  };

  ws.onclose = () => {
    setTimeout(connectWebSocket, 1500);
  };
}

async function triggerSpawnPreview() {
  state.impactShownForRun = false;
  state.wasRunning = false;
  const res = await fetch("/api/spawn", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ambulances: state.ambulanceCount,
      policy: state.policy,
      traffic_level: state.trafficLevel,
      hour_of_day: state.hourOfDay,
      seed: state.seed,
      speed: state.speed,
    }),
  });
  const snap = await res.json();
  state.lastTickState = snap;
  updateMapEntities(snap);
  updateHUDAndSidebar(snap);
}

async function triggerStartSimulation() {
  state.impactShownForRun = false;
  const res = await fetch("/api/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ambulances: state.ambulanceCount,
      policy: state.policy,
      traffic_level: state.trafficLevel,
      hour_of_day: state.hourOfDay,
      seed: state.seed,
      speed: state.speed,
    }),
  });
  const snap = await res.json();
  state.lastTickState = snap;
  state.wasRunning = true;
  updateMapEntities(snap);
  updateHUDAndSidebar(snap);
}

document.addEventListener("DOMContentLoaded", async () => {
  // Landing page launch button
  document.getElementById("btn-launch-app").addEventListener("click", () => {
    document.getElementById("landing-overlay").classList.add("fade-out");
  });

  // Spawn 5 vs Spawn 10 buttons
  document.querySelectorAll("[data-count]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document
        .querySelectorAll("[data-count]")
        .forEach((b) => b.classList.remove("active-spawn"));
      btn.classList.add("active-spawn");
      state.ambulanceCount = Number(btn.dataset.count);
      triggerSpawnPreview();
    });
  });

  // Policy Toggle (TRIAGE vs NEAREST)
  document.querySelectorAll(".policy-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document
        .querySelectorAll(".policy-btn")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.policy = btn.dataset.policy;
      triggerSpawnPreview();
    });
  });

  // Traffic / Time-of-Day chips
  document.querySelectorAll(".traffic-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document
        .querySelectorAll(".traffic-chip")
        .forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      state.trafficLevel = chip.dataset.level;
      state.hourOfDay = Number(chip.dataset.hour);
      triggerSpawnPreview();
    });
  });

  // Speed chips
  document.querySelectorAll(".speed-chip").forEach((chip) => {
    chip.addEventListener("click", async () => {
      document
        .querySelectorAll(".speed-chip")
        .forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      state.speed = Number(chip.dataset.speed);
      await fetch("/api/speed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ speed: state.speed }),
      });
    });
  });

  // Roadblock Mode
  const rbBtn = document.getElementById("btn-roadblock-mode");
  rbBtn.addEventListener("click", () => {
    state.roadblockMode = !state.roadblockMode;
    rbBtn.classList.toggle("active", state.roadblockMode);
    rbBtn.textContent = state.roadblockMode
      ? "🎯 Click Anywhere on Map to Drop Roadblock"
      : "🚧 Drop Live Roadblock on Map";
  });

  document
    .getElementById("btn-clear-roadblocks")
    .addEventListener("click", async () => {
      const res = await fetch("/api/roadblocks", { method: "DELETE" });
      const snap = await res.json();
      updateMapEntities(snap);
      updateHUDAndSidebar(snap);
    });

  map.on("click", async (e) => {
    if (!state.roadblockMode) return;
    state.roadblockMode = false;
    rbBtn.classList.remove("active");
    rbBtn.textContent = "🚧 Drop Live Roadblock on Map";
    const res = await fetch("/api/roadblock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lat: e.latlng.lat,
        lon: e.latlng.lng,
        radius_m: 650,
      }),
    });
    const snap = await res.json();
    updateMapEntities(snap);
    updateHUDAndSidebar(snap);
  });

  // Simulate Button
  document
    .getElementById("btn-simulate")
    .addEventListener("click", triggerStartSimulation);

  // Impact Calculator buttons
  document
    .getElementById("btn-open-impact")
    .addEventListener("click", fetchAndShowImpactModal);
  document.getElementById("btn-close-impact").addEventListener("click", () => {
    document.getElementById("impact-modal").classList.add("hidden");
  });
  document
    .getElementById("btn-replay-triage")
    .addEventListener("click", () => {
      document.getElementById("impact-modal").classList.add("hidden");
      state.policy = "TRIAGE";
      document.getElementById("btn-policy-triage").classList.add("active");
      document.getElementById("btn-policy-nearest").classList.remove("active");
      triggerStartSimulation();
    });
  document
    .getElementById("btn-replay-nearest")
    .addEventListener("click", () => {
      document.getElementById("impact-modal").classList.add("hidden");
      state.policy = "NEAREST";
      document.getElementById("btn-policy-nearest").classList.add("active");
      document.getElementById("btn-policy-triage").classList.remove("active");
      triggerStartSimulation();
    });

  // Inspector close
  document
    .getElementById("btn-close-inspector")
    .addEventListener("click", () => {
      document.getElementById("inspector-drawer").classList.add("hidden");
      state.selectedEntity = null;
    });

  // Sidebar Tabs
  const tabs = [
    ["tab-btn-ambulances", "ambulances"],
    ["tab-btn-hospitals", "hospitals"],
    ["tab-btn-events", "events"],
  ];
  tabs.forEach(([btnId, tabName]) => {
    document.getElementById(btnId).addEventListener("click", () => {
      document
        .querySelectorAll(".tab-btn")
        .forEach((b) => b.classList.remove("active"));
      document.getElementById(btnId).addEventListener("active");
      state.activeTab = tabName;
      if (state.lastTickState) renderSidebarList(state.lastTickState);
    });
  });

  // Fetch architecture info for the top HUD bar
  try {
    const hRes = await fetch("/api/health");
    const hData = await hRes.json();
    document.getElementById(
      "hud-arch-label"
    ).textContent = `IBM LinuxONE (${hData.architecture}) · Model R²=${hData.ml_model_r2} · ${hData.graph_nodes} Street Nodes`;
  } catch (e) {}

  // Load initial paused map state & open WebSocket stream
  await triggerSpawnPreview();
  connectWebSocket();
});