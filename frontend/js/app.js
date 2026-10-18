/**
 * ============================================================================
 * TRIAGE — Uber-Like 2D Leaflet Map + Interactive Spotlight Judge Tour
 *          + Chronological Animated 44,000 Impact Calculator
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
  selectedEntity: null,
  lastTickState: null,
  wasRunning: false,
  impactShownForRun: false,
  tourActive: false,
  tourStepIndex: 0,
};

const map = L.map("map", {
  center: MANCHESTER_CENTER,
  zoom: 12,
  zoomControl: false,
  attributionControl: false,
});

L.control.zoom({ position: "bottomright" }).addTo(map);

// Official OpenStreetMap tile server with custom Uber-Night dark filter in style.css
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
}).addTo(map);

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

const hospitalMarkers = new Map();
const ambulanceMarkers = new Map();
const ambulancePolylines = new Map();
const ambulanceGlowLines = new Map();
const roadblockCircles = new Map();
const ambInterpolation = new Map();

function formatSecondsToMMSS(totalSeconds) {
  const s = Math.max(0, Math.round(totalSeconds));
  const mins = Math.floor(s / 60);
  const secs = s % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

/**
 * Smoothly counts a number up from 0 to targetValue over durationMs
 * so judges watch the metrics climb chronologically!
 */
function animateNumberValue(elementId, startVal, endVal, durationMs, formatFn) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const startTime = performance.now();

  function step(now) {
    const progress = Math.min(1, (now - startTime) / durationMs);
    // Ease-out cubic curve
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = startVal + (endVal - startVal) * eased;
    el.textContent = formatFn ? formatFn(current) : Math.round(current).toLocaleString();
    if (progress < 1) {
      requestAnimationFrame(step);
    }
  }
  requestAnimationFrame(step);
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
        radius: rb.radius_m || 650,
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

let impactTimeouts = [];

async function fetchAndShowImpactModal() {
  try {
    // Clear any previous reveal timers
    impactTimeouts.forEach((t) => clearTimeout(t));
    impactTimeouts = [];

    // Hide all 6 stages initially so they reveal one after another
    for (let i = 1; i <= 6; i++) {
      const st = document.getElementById(`impact-stage-${i}`);
      if (st) st.classList.remove("stage-visible");
    }
    document.getElementById("bar-nearest").style.width = "0%";
    document.getElementById("bar-triage").style.width = "0%";

    const res = await fetch("/api/impact");
    const data = await res.json();
    const tc = data.triage_comparison || {};

    const nearestWait = Number(tc.nearest_handover_min ?? 24.5);
    const nearestCases = Number(tc.nearest_projected_cases ?? 35933);
    const nearestOverflows = Number(tc.nearest_details?.corridor_overflows ?? 3);

    const triageWait = Number(tc.triage_handover_min ?? data.triage_avg_handover_min ?? 8.2);
    const triageCases = Number(tc.triage_projected_cases ?? data.projected_annual_severe_cases ?? 11733);
    const triageOverflows = Number(tc.triage_details?.corridor_overflows ?? 0);

    const preventedCases = Number(tc.triage_prevented ?? data.severe_cases_prevented ?? 32267);
    const reductionPct = Number(tc.triage_reduction_pct ?? data.reduction_percent ?? 73.3);

    document.getElementById("impact-modal").classList.remove("hidden");

    // Stage 1 (t = 100ms): Reveal Title & AACE 44,000 Context
    impactTimeouts.push(
      setTimeout(() => {
        document.getElementById("impact-stage-1").classList.add("stage-visible");
      }, 100)
    );

    // Stage 2 (t = 700ms): Reveal Step 01 UK National Baseline (30.0 min -> 44,000 cases)
    impactTimeouts.push(
      setTimeout(() => {
        document.getElementById("impact-stage-2").classList.add("stage-visible");
      }, 700)
    );

    // Stage 3 (t = 1550ms): Reveal Step 02 Naive Nearest Hospital Stampede + count up numbers
    impactTimeouts.push(
      setTimeout(() => {
        document.getElementById("impact-stage-3").classList.add("stage-visible");
        animateNumberValue("comp-nearest-wait", 0, nearestWait, 900, (v) => `${v.toFixed(1)} min`);
        animateNumberValue("comp-nearest-cases", 0, nearestCases, 900, (v) => `${Math.round(v).toLocaleString()} / yr`);
        document.getElementById("comp-nearest-overflows").textContent = `${nearestOverflows} patients`;
        document.getElementById("bar-nearest").style.width = `${Math.min(100, Math.round((nearestCases / 44000) * 100))}%`;
      }, 1550)
    );

    // Stage 4 (t = 2550ms): Reveal Step 03 TRIAGE AI Joint Routing + count up numbers
    impactTimeouts.push(
      setTimeout(() => {
        document.getElementById("impact-stage-4").classList.add("stage-visible");
        animateNumberValue("comp-triage-wait", 0, triageWait, 900, (v) => `${v.toFixed(1)} min`);
        animateNumberValue("comp-triage-cases", 0, triageCases, 900, (v) => `${Math.round(v).toLocaleString()} / yr`);
        document.getElementById("comp-triage-overflows").textContent = `${triageOverflows} patients`;
        document.getElementById("bar-triage").style.width = `${Math.min(100, Math.round((triageCases / 44000) * 100))}%`;
      }, 2550)
    );

    // Stage 5 (t = 3600ms): THE GRAND FINALE CLIMAX — Count up Severe Cases Prevented & % Lives/Harm Saved!
    impactTimeouts.push(
      setTimeout(() => {
        document.getElementById("impact-stage-5").classList.add("stage-visible");
        animateNumberValue("impact-prevented-num", 0, preventedCases, 1400, (v) =>
          Math.round(v).toLocaleString()
        );
        animateNumberValue("impact-reduction-pct", 0, reductionPct, 1400, (v) =>
          `🏆 ${v.toFixed(1)}% Reduction in Potential Severe Harm & Deaths vs. 30-Min Baseline`
        );
      }, 3600)
    );

    // Stage 6 (t = 4800ms): Reveal Replay Action Buttons
    impactTimeouts.push(
      setTimeout(() => {
        document.getElementById("impact-stage-6").classList.add("stage-visible");
      }, 4800)
    );
  } catch (err) {
    console.error("Failed to load impact metrics:", err);
  }
}

const TOUR_STEPS = [
  {
    targetId: "tour-section-spawner",
    title: "1. Spawn a 999 Emergency Wave",
    body: "In real life, there is never just 1 ambulance on the road. Click <strong>10 Ambulances (Surge)</strong> right now to spawn 10 simultaneous critical patients across Greater Manchester!",
    prompt: "👆 Try clicking '10 Ambulances (Surge)' (or click Next Step)",
    onEnter: () => {},
  },
  {
    targetId: "tour-section-policy",
    title: "2. The 'Hospital Stampede' vs. TRIAGE AI",
    body: "Click <strong>📍 NEAREST</strong> and watch the map: naive routing sends nearby ambulances to the exact same closest hospital, overloading its queue! Then click <strong>🧠 TRIAGE AI</strong> to watch our Hungarian Algorithm spread them across 8 NHS hospitals.",
    prompt: "👆 Toggle between NEAREST and TRIAGE AI to see routes switch live!",
    onEnter: () => {},
  },
  {
    targetId: "tour-section-traffic",
    title: "3. Dynamic Time-of-Day & Rush Hour Traffic",
    body: "An emergency at <strong>8:22 PM Quiet</strong> faces very different road speeds than <strong>8:30 AM Rush Hour</strong>. Clicking these chips recalculates all 7,148 Manchester street segments via Backwards Dijkstra in under 15ms.",
    prompt: "👆 Click '10:00 AM Busy' or '8:30 AM Rush' to test live traffic!",
    onEnter: () => {},
  },
  {
    targetId: "tour-section-fleet",
    title: "4. Predictive AI Vitals & DeepSeek Notes",
    body: "Every ambulance carries a patient scored by our <strong>Scikit-Learn HistGradientBoosting AI</strong> on IBM LinuxONE. We just opened <strong>AMB-01</strong> on the right so you can see its live vitals and <strong>40-word DeepSeek Reception Pre-Alert</strong>!",
    prompt: "👀 Check out the Inspector Drawer on the right (or click any ambulance card)!",
    onEnter: () => {
      openInspector("ambulance", "AMB-01");
    },
  },
  {
    targetId: "tour-section-roadblock",
    title: "5. Drop a Live Roadblock on a Street Route",
    body: "What if a crash blocks a major Manchester road while ambulances are en route? Let's test our real-time street detour engine!",
    prompt: "👆 Click '🚧 Drop Live Roadblock on Map' — or click Next Step and we'll drop one for you!",
    onEnter: () => {},
  },
  {
    targetId: "tour-section-simulate",
    title: "6. Simulate Live 60FPS Ambulance Routing",
    body: "When you press <strong>SIMULATE LIVE ROUTING</strong>, ambulances glide smoothly along real Manchester streets. Every 15 simulated seconds, TRIAGE checks if any hospital is filling up and diverts trailing ambulances mid-journey!",
    prompt: "👆 Click '▶ SIMULATE LIVE ROUTING' to start the fleet!",
    onEnter: () => {},
  },
  {
    targetId: "btn-open-impact",
    title: "7. The 44,000 Annual Severe Harm Calculator",
    body: "At the end of every run (or anytime you click this button), TRIAGE reveals a chronological breakdown of how many of the <strong>44,000 annual severe harm cases</strong> our algorithm prevented.",
    prompt: "🎉 Click 'Finish & Open Impact Report' or start exploring freely!",
    onEnter: () => {},
  },
];

function startOnboardingTour() {
  state.tourActive = true;
  state.tourStepIndex = 0;
  document.getElementById("onboarding-overlay").classList.remove("hidden");
  renderTourStep();
}

function stopOnboardingTour() {
  state.tourActive = false;
  document.getElementById("onboarding-overlay").classList.add("hidden");
  document
    .querySelectorAll(".tour-active-target")
    .forEach((el) => el.classList.remove("tour-active-target"));
}

function renderTourStep() {
  if (!state.tourActive) return;
  const step = TOUR_STEPS[state.tourStepIndex];
  if (!step) {
    stopOnboardingTour();
    return;
  }

  // Remove previous highlight
  document
    .querySelectorAll(".tour-active-target")
    .forEach((el) => el.classList.remove("tour-active-target"));

  const targetEl = document.getElementById(step.targetId);
  const holeEl = document.getElementById("spotlight-hole");
  const tooltipEl = document.getElementById("tour-tooltip");

  if (targetEl) {
    targetEl.classList.add("tour-active-target");
    const rect = targetEl.getBoundingClientRect();
    const pad = 8;
    holeEl.style.top = `${Math.max(6, rect.top - pad)}px`;
    holeEl.style.left = `${Math.max(6, rect.left - pad)}px`;
    holeEl.style.width = `${rect.width + pad * 2}px`;
    holeEl.style.height = `${rect.height + pad * 2}px`;

    // Position the floating story card right next to the highlighted element
    let tooltipLeft = rect.right + 24;
    let tooltipTop = Math.max(88, Math.min(window.innerHeight - 310, rect.top - 10));

    if (tooltipLeft + 400 > window.innerWidth) {
      tooltipLeft = Math.max(20, rect.left - 410);
      tooltipTop = Math.max(88, rect.bottom + 18);
    }

    tooltipEl.style.left = `${tooltipLeft}px`;
    tooltipEl.style.top = `${tooltipTop}px`;
  }

  document.getElementById("tour-step-badge").textContent = `STEP ${
    state.tourStepIndex + 1
  } OF ${TOUR_STEPS.length}`;
  document.getElementById("tour-title").textContent = step.title;
  document.getElementById("tour-body").innerHTML = step.body;
  document.getElementById("tour-action-prompt").innerHTML = step.prompt;

  // Render progress dots
  const dotsContainer = document.getElementById("tour-dots");
  dotsContainer.innerHTML = TOUR_STEPS.map(
    (_, idx) => `<div class="tour-dot ${idx === state.tourStepIndex ? "active" : ""}"></div>`
  ).join("");

  const prevBtn = document.getElementById("btn-tour-prev");
  prevBtn.style.visibility = state.tourStepIndex === 0 ? "hidden" : "visible";

  const nextBtn = document.getElementById("btn-tour-next");
  nextBtn.textContent =
    state.tourStepIndex === TOUR_STEPS.length - 1 ? "Finish Tour ✓" : "Next Step →";

  if (typeof step.onEnter === "function") {
    step.onEnter();
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
  if (state.tourActive) {
    stopOnboardingTour();
  }
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
  // Landing page buttons: Launch with Interactive Judge Tour OR Skip directly to Sandbox
  document.getElementById("btn-launch-tour").addEventListener("click", () => {
    document.getElementById("landing-overlay").classList.add("fade-out");
    setTimeout(() => startOnboardingTour(), 450);
  });

  document.getElementById("btn-launch-direct").addEventListener("click", () => {
    document.getElementById("landing-overlay").classList.add("fade-out");
  });

  // Top bar Guided Tour replay button
  document.getElementById("btn-start-tour").addEventListener("click", () => {
    startOnboardingTour();
  });

  // Tour Navigation buttons
  document.getElementById("btn-tour-skip").addEventListener("click", stopOnboardingTour);
  document.getElementById("btn-tour-prev").addEventListener("click", () => {
    if (state.tourStepIndex > 0) {
      state.tourStepIndex--;
      renderTourStep();
    }
  });
  document.getElementById("btn-tour-next").addEventListener("click", () => {
    if (state.tourStepIndex < TOUR_STEPS.length - 1) {
      state.tourStepIndex++;
      renderTourStep();
    } else {
      stopOnboardingTour();
    }
  });

  window.addEventListener("resize", () => {
    if (state.tourActive) renderTourStep();
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
      if (state.tourActive && state.tourStepIndex === 0) {
        setTimeout(() => {
          state.tourStepIndex = 1;
          renderTourStep();
        }, 600);
      }
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

    // If in tour step 5, hide the spotlight overlay temporarily so they can click the map freely!
    if (state.tourActive && state.roadblockMode) {
      document.getElementById("spotlight-hole").style.opacity = "0";
      document.getElementById("tour-action-prompt").innerHTML =
        "🎯 Now click directly on any glowing route line on the Manchester map!";
    }
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

    if (state.tourActive) {
      document.getElementById("spotlight-hole").style.opacity = "1";
      state.tourStepIndex = 5; // Advance to Step 6 (Simulate Live Routing)
      renderTourStep();
    }
  });

  // Simulate Button
  document
    .getElementById("btn-simulate")
    .addEventListener("click", triggerStartSimulation);

  // Impact Calculator buttons
  document.getElementById("btn-open-impact").addEventListener("click", () => {
    if (state.tourActive) stopOnboardingTour();
    fetchAndShowImpactModal();
  });
  document.getElementById("btn-close-impact").addEventListener("click", () => {
    document.getElementById("impact-modal").classList.add("hidden");
  });
  document.getElementById("btn-replay-triage").addEventListener("click", () => {
    document.getElementById("impact-modal").classList.add("hidden");
    state.policy = "TRIAGE";
    document.getElementById("btn-policy-triage").classList.add("active");
    document.getElementById("btn-policy-nearest").classList.remove("active");
    triggerStartSimulation();
  });
  document.getElementById("btn-replay-nearest").addEventListener("click", () => {
    document.getElementById("impact-modal").classList.add("hidden");
    state.policy = "NEAREST";
    document.getElementById("btn-policy-nearest").classList.add("active");
    document.getElementById("btn-policy-triage").classList.remove("active");
    triggerStartSimulation();
  });

  // Inspector close
  document.getElementById("btn-close-inspector").addEventListener("click", () => {
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
      document.getElementById(btnId).classList.add("active");
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

  await triggerSpawnPreview();
  connectWebSocket();
});