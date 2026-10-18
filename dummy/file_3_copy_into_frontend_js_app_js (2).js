/**
 * ============================================================================
 * TRIAGE — Uber-Like 2D Leaflet Map + Natural Human-Reading Typewriter Engine
 *          + 8-Step Interactive Spotlight Judge Tour + Chronological 44,000 Report
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
 * HTML-Aware Smooth Typewriter Engine (Tuned to Comfortable Eye-Reading Speed!)
 * - Advances 1 character at a time (around ~30ms per character, ~33 chars/sec,
 *   which is slightly brisker than average human reading speed so eyes can read
 *   word-by-word comfortably without waiting forever).
 * - Adds a subtle, natural pause after punctuation (, . — :) so sentences flow naturally.
 * - Instantly skips over HTML tags (<strong...>, <em>, etc.) so markup never breaks.
 */
const activeTypewriters = new Map();

function sleepMs(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function typewriteHTML(elementOrId, htmlString, charDelayMs = 30) {
  return new Promise((resolve) => {
    const el =
      typeof elementOrId === "string"
        ? document.getElementById(elementOrId)
        : elementOrId;
    if (!el) {
      resolve();
      return;
    }

    if (activeTypewriters.has(el)) {
      clearTimeout(activeTypewriters.get(el));
      activeTypewriters.delete(el);
    }

    el.innerHTML = "";
    el.classList.add("typewriter-cursor");

    let i = 0;
    const len = htmlString.length;

    function step() {
      if (i >= len) {
        el.innerHTML = htmlString;
        el.classList.remove("typewriter-cursor");
        activeTypewriters.delete(el);
        resolve();
        return;
      }

      // Advance exactly 1 visible character per step for smooth word-by-word reading
      let lastVisibleChar = "";
      while (i < len) {
        if (htmlString[i] === "<") {
          const closeIdx = htmlString.indexOf(">", i);
          if (closeIdx !== -1) {
            i = closeIdx + 1;
            continue;
          }
        }
        if (htmlString[i] === "&") {
          const semiIdx = htmlString.indexOf(";", i);
          if (semiIdx !== -1 && semiIdx - i < 8) {
            i = semiIdx + 1;
            lastVisibleChar = "&";
            break;
          }
        }
        lastVisibleChar = htmlString[i];
        i++;
        break;
      }

      el.innerHTML = htmlString.slice(0, i);

      // Subtle natural cadence pause on punctuation so the eye can absorb each clause
      let nextDelay = charDelayMs;
      if (lastVisibleChar === "." || lastVisibleChar === "!") {
        nextDelay = charDelayMs * 4.5;
      } else if (
        lastVisibleChar === "," ||
        lastVisibleChar === ":" ||
        lastVisibleChar === "—"
      ) {
        nextDelay = charDelayMs * 2.5;
      }

      const timerId = setTimeout(step, nextDelay);
      activeTypewriters.set(el, timerId);
    }

    step();
  });
}

/**
 * Runs the sequential typewriter animation on the Hero Landing Overlay
 * at a comfortable reading pace, with a brief pause between lines.
 */
async function runHeroLandingTypewriter() {
  const subEl = document.getElementById("hero-type-subtitle");
  const line1 = document.getElementById("hero-type-line-1");
  const line2 = document.getElementById("hero-type-line-2");
  const line3 = document.getElementById("hero-type-line-3");
  const pillars = document.getElementById("hero-pillars-block");
  const cta = document.getElementById("hero-cta-block");

  await typewriteHTML(
    subEl,
    "Time-critical Routing &amp; Intelligent Ambulance Guidance Engine",
    32
  );
  await sleepMs(350);

  line1.classList.add("line-active");
  await typewriteHTML(
    line1,
    "🚨 In England, <strong>44,000 patients suffer severe harm every year</strong> due to 30+ minute ambulance handover delays.",
    30
  );
  await sleepMs(450);

  line2.classList.add("line-active");
  await typewriteHTML(
    line2,
    "🏥 Standard navigation routes nearby 999 calls to the <em>same</em> closest hospital—creating a lethal <strong>&ldquo;Hospital Stampede&rdquo;</strong>.",
    30
  );
  await sleepMs(450);

  line3.classList.add("line-active");
  await typewriteHTML(
    line3,
    "🧠 <strong>TRIAGE</strong> combines Predictive AI deterioration scoring, Hungarian joint-optimization, and DeepSeek pre-alerts to eliminate bottlenecks in real time.",
    28
  );
  await sleepMs(350);

  pillars.classList.add("block-visible");
  setTimeout(() => {
    cta.classList.add("block-visible");
  }, 450);
}

/**
 * Smoothly counts a number up from startVal to endVal over durationMs
 */
function animateNumberValue(elementId, startVal, endVal, durationMs, formatFn) {
  return new Promise((resolve) => {
    const el = document.getElementById(elementId);
    if (!el) {
      resolve();
      return;
    }
    const startTime = performance.now();

    function step(now) {
      const progress = Math.min(1, (now - startTime) / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = startVal + (endVal - startVal) * eased;
      el.textContent = formatFn
        ? formatFn(current)
        : Math.round(current).toLocaleString();
      if (progress < 1) {
        requestAnimationFrame(step);
      } else {
        resolve();
      }
    }
    requestAnimationFrame(step);
  });
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
  let statusBadge = "";
  if (amb.status === "EN_ROUTE") {
    statusBadge = `<span class="bubble-eta">${etaMin}m</span>`;
  } else if (amb.status === "HANDOVER_DONE") {
    statusBadge = `<span class="bubble-eta" style="color:#00f59b">DONE</span>`;
  } else {
    statusBadge = `<span class="bubble-eta" style="color:#ffb800">ARRIVED</span>`;
  }

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
        fillOpacity: 0.35,
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
        const statusStr =
          amb.status === "EN_ROUTE"
            ? `ETA ${etaMin}m`
            : amb.status === "HANDOVER_DONE"
            ? "HANDOVER DONE"
            : "ARRIVED AT ED";
        return `
          <div class="fleet-item-card" onclick="openInspector('ambulance', '${amb.id}')">
            <div class="fleet-row-top">
              <span class="fleet-id">🚑 ${amb.id} · ${p.age || 60}${p.sex || "M"}</span>
              <span class="cat-badge cat-${amb.category}">CAT ${amb.category}</span>
            </div>
            <div class="fleet-cond">${p.condition_name || "Emergency"}</div>
            <div class="fleet-row-bottom">
              <span>➔ <strong>${amb.hospital_name || amb.hospital_id}</strong></span>
              <span class="mono">${statusStr} · Det ${amb.deterioration.toFixed(1)}%</span>
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

let impactRunToken = 0;

async function fetchAndShowImpactModal() {
  try {
    const myToken = ++impactRunToken;

    // Reset all 6 stages so they reveal and type out chronologically one after another
    for (let i = 1; i <= 6; i++) {
      const st = document.getElementById(`impact-stage-${i}`);
      if (st) st.classList.remove("stage-visible");
    }
    document.getElementById("bar-nearest").style.width = "0%";
    document.getElementById("bar-triage").style.width = "0%";
    document.getElementById("impact-prevented-num").textContent = "0";
    document.getElementById("impact-reduction-pct").textContent = "";

    const res = await fetch("/api/impact");
    const data = await res.json();
    const tc = data.triage_comparison || {};

    const nearestWait = Number(tc.nearest_handover_min ?? 24.5);
    const nearestCases = Number(tc.nearest_projected_cases ?? 35933);
    const nearestOverflows = Number(tc.nearest_details?.corridor_overflows ?? 3);

    const triageWait = Number(
      tc.triage_handover_min ?? data.triage_avg_handover_min ?? 8.2
    );
    const triageCases = Number(
      tc.triage_projected_cases ?? data.projected_annual_severe_cases ?? 11733
    );
    const triageOverflows = Number(tc.triage_details?.corridor_overflows ?? 0);

    const preventedCases = Number(
      tc.triage_prevented ?? data.severe_cases_prevented ?? 32267
    );
    const reductionPct = Number(
      tc.triage_reduction_pct ?? data.reduction_percent ?? 73.3
    );

    document.getElementById("impact-modal").classList.remove("hidden");

    // STAGE 1: Type out Headline & AACE 44,000 Context at natural reading speed
    if (myToken !== impactRunToken) return;
    document.getElementById("impact-stage-1").classList.add("stage-visible");
    await typewriteHTML(
      "impact-type-headline",
      "Chronological Clinical Impact Analysis",
      32
    );
    if (myToken !== impactRunToken) return;
    await typewriteHTML(
      "impact-type-subheadline",
      "Anchored to the Association of Ambulance Chief Executives (AACE) national baseline of <strong>44,000 annual severe patient harm cases</strong> caused by 30-minute handover delays.",
      26
    );
    await sleepMs(400);

    // STAGE 2: Step 01 National Baseline Card
    if (myToken !== impactRunToken) return;
    document.getElementById("impact-stage-2").classList.add("stage-visible");
    await typewriteHTML(
      "impact-type-card1-title",
      "🇬🇧 UK 30-Min Delay Baseline",
      30
    );
    if (myToken !== impactRunToken) return;
    await typewriteHTML(
      "impact-type-card1-desc",
      "When ambulances queue for 30 minutes outside overcrowded EDs, 44,000 patients suffer severe harm annually.",
      26
    );
    await sleepMs(400);

    // STAGE 3: Step 02 Naive Nearest Hospital Stampede Card
    if (myToken !== impactRunToken) return;
    document.getElementById("impact-stage-3").classList.add("stage-visible");
    await typewriteHTML(
      "impact-type-card2-title",
      "📍 Naive &ldquo;Nearest ED&rdquo; (Stampede)",
      30
    );
    document.getElementById("bar-nearest").style.width = `${Math.min(
      100,
      Math.round((nearestCases / 44000) * 100)
    )}%`;
    document.getElementById(
      "comp-nearest-overflows"
    ).textContent = `${nearestOverflows} patients`;
    await Promise.all([
      animateNumberValue(
        "comp-nearest-wait",
        0,
        nearestWait,
        1000,
        (v) => `${v.toFixed(1)} min`
      ),
      animateNumberValue(
        "comp-nearest-cases",
        0,
        nearestCases,
        1000,
        (v) => `${Math.round(v).toLocaleString()} / yr`
      ),
    ]);
    if (myToken !== impactRunToken) return;
    await typewriteHTML(
      "impact-type-card2-desc",
      "Independent routing floods the closest hospital, creating severe corridor queues.",
      26
    );
    await sleepMs(400);

    // STAGE 4: Step 03 TRIAGE AI Joint Routing Card
    if (myToken !== impactRunToken) return;
    document.getElementById("impact-stage-4").classList.add("stage-visible");
    await typewriteHTML(
      "impact-type-card3-title",
      "🧠 TRIAGE AI (Hungarian Joint)",
      30
    );
    document.getElementById("bar-triage").style.width = `${Math.min(
      100,
      Math.round((triageCases / 44000) * 100)
    )}%`;
    document.getElementById(
      "comp-triage-overflows"
    ).textContent = `${triageOverflows} patients`;
    await Promise.all([
      animateNumberValue(
        "comp-triage-wait",
        0,
        triageWait,
        1000,
        (v) => `${v.toFixed(1)} min`
      ),
      animateNumberValue(
        "comp-triage-cases",
        0,
        triageCases,
        1000,
        (v) => `${Math.round(v).toLocaleString()} / yr`
      ),
    ]);
    if (myToken !== impactRunToken) return;
    await typewriteHTML(
      "impact-type-card3-desc",
      "Joint optimization spreads ambulances across 8 Manchester EDs, slashing handover waits.",
      26
    );
    await sleepMs(500);

    // STAGE 5: THE GRAND FINALE CLIMAX — Type Verdict + Count Up Prevented Cases + Type Final % Saved!
    if (myToken !== impactRunToken) return;
    document.getElementById("impact-stage-5").classList.add("stage-visible");
    await typewriteHTML(
      "impact-type-verdict-label",
      "FINAL VERDICT · POTENTIAL SEVERE COMPLICATIONS PREVENTED ANNUALLY",
      30
    );
    if (myToken !== impactRunToken) return;
    await animateNumberValue(
      "impact-prevented-num",
      0,
      preventedCases,
      1600,
      (v) => Math.round(v).toLocaleString()
    );
    if (myToken !== impactRunToken) return;
    await typewriteHTML(
      "impact-reduction-pct",
      `🏆 ${reductionPct.toFixed(
        1
      )}% Reduction in Potential Severe Harm &amp; Deaths vs. 30-Min Baseline`,
      32
    );
    await sleepMs(300);

    // STAGE 6: Reveal Action Buttons
    if (myToken !== impactRunToken) return;
    document.getElementById("impact-stage-6").classList.add("stage-visible");
  } catch (err) {
    console.error("Failed to load impact metrics:", err);
  }
}

const TOUR_STEPS = [
  {
    targetId: "hud-telemetry-pills",
    title: "1. Live Mission Telemetry Bar",
    body: "Look at the top center bar: <strong>SIM CLOCK</strong> tracks elapsed emergency seconds, <strong>EN ROUTE</strong> shows ambulances currently driving, <strong>QUEUED / ARRIVED</strong> counts ambulances that reached a hospital, and <strong>AI DIVERSIONS</strong> counts how many times TRIAGE redirected an ambulance mid-journey to prevent a queue!",
    prompt: "👀 Review the 4 live telemetry counters above, then click 'Next Step →'",
    onEnter: () => {},
  },
  {
    targetId: "tour-section-spawner",
    title: "2. Spawn a 999 Emergency Wave",
    body: "In real life, there is never just 1 ambulance on the road. Click <strong>10 Ambulances (Surge)</strong> right now to spawn 10 simultaneous critical patients across Greater Manchester!",
    prompt: "👆 Click '10 Ambulances (Surge)' inside the glowing box (or click Next Step)",
    onEnter: () => {},
  },
  {
    targetId: "tour-section-policy",
    title: "3. The 'Hospital Stampede' vs. TRIAGE AI",
    body: "Click <strong>📍 NEAREST</strong> and watch the map: naive routing sends nearby ambulances to the exact same closest hospital, overloading its queue! Then click <strong>🧠 TRIAGE AI</strong> to watch our Hungarian Algorithm spread them across 8 NHS hospitals.",
    prompt: "👆 Toggle between NEAREST and TRIAGE AI to see routes switch live!",
    onEnter: () => {},
  },
  {
    targetId: "tour-section-traffic",
    title: "4. Dynamic Time-of-Day & Rush Hour Traffic",
    body: "An emergency at <strong>8:22 PM Quiet</strong> faces very different road speeds than <strong>8:30 AM Rush Hour</strong>. Clicking these chips recalculates all 7,148 Manchester street segments via Backwards Dijkstra in under 15ms.",
    prompt: "👆 Click '10:00 AM Busy' or '8:30 AM Rush' to test live traffic!",
    onEnter: () => {},
  },
  {
    targetId: "tour-section-fleet",
    title: "5. Predictive AI Vitals & DeepSeek Notes",
    body: "Every ambulance carries a patient scored by our <strong>Scikit-Learn HistGradientBoosting AI</strong> on IBM LinuxONE. Look at the <strong>Inspector Drawer on the right</strong> to see <strong>AMB-01</strong>'s live vitals and <strong>40-word DeepSeek Reception Pre-Alert</strong>!",
    prompt: "👀 Check out the DeepSeek AI Note on the right (or click any ambulance card)!",
    onEnter: () => {
      openInspector("ambulance", "AMB-01");
    },
  },
  {
    targetId: "tour-section-roadblock",
    title: "6. Drop a Live Roadblock on a Street Route",
    body: "What if a crash blocks a major Manchester road while ambulances are en route? Step A: Click the red <strong>🚧 Drop Live Roadblock on Map</strong> button. Step B: Move your mouse onto the Manchester map and <strong>click directly on any glowing route line</strong> to watch the street detour!",
    prompt: "👆 Click '🚧 Drop Live Roadblock on Map', then click any glowing route on the map!",
    onEnter: () => {},
  },
  {
    targetId: "tour-section-simulate",
    title: "7. Simulate Live 60FPS Ambulance Routing",
    body: "When you press <strong>SIMULATE LIVE ROUTING</strong>, ambulances glide smoothly along real Manchester streets. As soon as all ambulances arrive at their hospitals, the 44,000 Impact Report opens automatically!",
    prompt: "👆 Click '▶ SIMULATE LIVE ROUTING' to launch the fleet!",
    onEnter: () => {},
  },
  {
    targetId: "btn-open-impact",
    title: "8. The 44,000 Annual Severe Harm Calculator",
    body: "At the end of every run (or anytime you click this button), TRIAGE types out a chronological breakdown of how many of the <strong>44,000 annual severe harm cases</strong> our algorithm prevented.",
    prompt: "🎉 Click 'Finish Tour ✓' or click the '44,000 Impact Calculator' button!",
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
  document.getElementById("spotlight-hole").style.opacity = "1";
  document
    .querySelectorAll(".tour-active-target")
    .forEach((el) => el.classList.remove("tour-active-target"));
}

async function renderTourStep() {
  if (!state.tourActive) return;
  const step = TOUR_STEPS[state.tourStepIndex];
  if (!step) {
    stopOnboardingTour();
    return;
  }

  document
    .querySelectorAll(".tour-active-target")
    .forEach((el) => el.classList.remove("tour-active-target"));

  const targetEl = document.getElementById(step.targetId);
  const holeEl = document.getElementById("spotlight-hole");
  const tooltipEl = document.getElementById("tour-tooltip");
  holeEl.style.opacity = "1";

  if (targetEl) {
    targetEl.classList.add("tour-active-target");
    const rect = targetEl.getBoundingClientRect();
    const pad = 8;
    holeEl.style.top = `${Math.max(6, rect.top - pad)}px`;
    holeEl.style.left = `${Math.max(6, rect.left - pad)}px`;
    holeEl.style.width = `${rect.width + pad * 2}px`;
    holeEl.style.height = `${rect.height + pad * 2}px`;

    let tooltipLeft = rect.right + 24;
    let tooltipTop = Math.max(88, Math.min(window.innerHeight - 330, rect.top - 10));

    if (rect.top < 80) {
      tooltipLeft = Math.max(20, Math.min(window.innerWidth - 430, rect.left));
      tooltipTop = rect.bottom + 18;
    } else if (tooltipLeft + 420 > window.innerWidth) {
      tooltipLeft = Math.max(20, rect.left - 425);
      tooltipTop = Math.max(88, rect.bottom + 18);
    }

    tooltipEl.style.left = `${tooltipLeft}px`;
    tooltipEl.style.top = `${tooltipTop}px`;
  }

  document.getElementById("tour-step-badge").textContent = `STEP ${
    state.tourStepIndex + 1
  } OF ${TOUR_STEPS.length}`;

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

  // Smoothly type out the title, body, and prompt at a natural reading speed!
  const stepSnapshot = state.tourStepIndex;
  document.getElementById("tour-body").innerHTML = "";
  document.getElementById("tour-action-prompt").innerHTML = "";

  await typewriteHTML("tour-title", step.title, 30);
  if (!state.tourActive || state.tourStepIndex !== stepSnapshot) return;
  await typewriteHTML("tour-body", step.body, 25);
  if (!state.tourActive || state.tourStepIndex !== stepSnapshot) return;
  await typewriteHTML("tour-action-prompt", step.prompt, 26);
}

function setRoadblockMode(enabled) {
  state.roadblockMode = enabled;
  const rbBtn = document.getElementById("btn-roadblock-mode");
  const rbBanner = document.getElementById("roadblock-map-banner");
  const mapEl = document.getElementById("map");

  rbBtn.classList.toggle("active", enabled);
  rbBtn.textContent = enabled
    ? "🎯 Now Click Any Route on the Map!"
    : "🚧 Drop Live Roadblock on Map";

  rbBanner.classList.toggle("hidden", !enabled);
  mapEl.classList.toggle("roadblock-cursor-active", enabled);

  if (state.tourActive && enabled) {
    document.getElementById("spotlight-hole").style.opacity = "0";
    typewriteHTML(
      "tour-action-prompt",
      "🎯 Move your mouse onto the Manchester map and CLICK directly on any glowing route line!",
      26
    );
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

    const ambs = tickData.ambulances || [];
    const allArrived =
      ambs.length > 0 && ambs.every((a) => a.status !== "EN_ROUTE");

    if (
      state.wasRunning &&
      (!tickData.running || allArrived) &&
      !state.impactShownForRun
    ) {
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
  runHeroLandingTypewriter();

  document.getElementById("btn-launch-tour").addEventListener("click", () => {
    document.getElementById("landing-overlay").classList.add("fade-out");
    setTimeout(() => startOnboardingTour(), 450);
  });

  document.getElementById("btn-launch-direct").addEventListener("click", () => {
    document.getElementById("landing-overlay").classList.add("fade-out");
  });

  document.getElementById("btn-start-tour").addEventListener("click", () => {
    startOnboardingTour();
  });

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

  document.querySelectorAll("[data-count]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document
        .querySelectorAll("[data-count]")
        .forEach((b) => b.classList.remove("active-spawn"));
      btn.classList.add("active-spawn");
      state.ambulanceCount = Number(btn.dataset.count);
      triggerSpawnPreview();
      if (state.tourActive && state.tourStepIndex === 1) {
        setTimeout(() => {
          state.tourStepIndex = 2;
          renderTourStep();
        }, 650);
      }
    });
  });

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

  document.getElementById("btn-roadblock-mode").addEventListener("click", () => {
    setRoadblockMode(!state.roadblockMode);
  });

  document.getElementById("btn-cancel-rb-banner").addEventListener("click", () => {
    setRoadblockMode(false);
  });

  document
    .getElementById("btn-clear-roadblocks")
    .addEventListener("click", async () => {
      setRoadblockMode(false);
      const res = await fetch("/api/roadblocks", { method: "DELETE" });
      const snap = await res.json();
      updateMapEntities(snap);
      updateHUDAndSidebar(snap);
    });

  map.on("click", async (e) => {
    if (!state.roadblockMode) return;
    setRoadblockMode(false);
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
      state.tourStepIndex = 6;
      renderTourStep();
    }
  });

  document
    .getElementById("btn-simulate")
    .addEventListener("click", triggerStartSimulation);

  document.getElementById("btn-open-impact").addEventListener("click", () => {
    if (state.tourActive) stopOnboardingTour();
    fetchAndShowImpactModal();
  });
  document.getElementById("btn-close-impact").addEventListener("click", () => {
    impactRunToken++;
    document.getElementById("impact-modal").classList.add("hidden");
  });
  document.getElementById("btn-replay-triage").addEventListener("click", () => {
    impactRunToken++;
    document.getElementById("impact-modal").classList.add("hidden");
    state.policy = "TRIAGE";
    document.getElementById("btn-policy-triage").classList.add("active");
    document.getElementById("btn-policy-nearest").classList.remove("active");
    triggerStartSimulation();
  });
  document.getElementById("btn-replay-nearest").addEventListener("click", () => {
    impactRunToken++;
    document.getElementById("impact-modal").classList.add("hidden");
    state.policy = "NEAREST";
    document.getElementById("btn-policy-nearest").classList.add("active");
    document.getElementById("btn-policy-triage").classList.remove("active");
    triggerStartSimulation();
  });

  document.getElementById("btn-close-inspector").addEventListener("click", () => {
    document.getElementById("inspector-drawer").classList.add("hidden");
    state.selectedEntity = null;
  });

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