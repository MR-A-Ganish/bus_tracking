const API = "";
let myAssignment = null;
let routeStops = [];
let html5QrCode = null;

let map = null;
let busMarker = null;
let stopMarkers = {};

let lastLoc = null;
let lastNotifications = [];
let arrivalWaved = false;

const RING_CIRC = 264;

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, { credentials: "include", ...options });
  if (res.status === 401) {
    window.location.href = "index.html";
    throw new Error("Not logged in");
  }
  return res.json();
}

function playBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.2, ctx.currentTime);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
    osc.stop(ctx.currentTime + 0.35);
  } catch (e) { /* audio not critical */ }
}

/* ---------------- Greeting banner + mini mascot ---------------- */

function updateGreeting(name) {
  const hour = new Date().getHours();
  const banner = document.getElementById("greeting-banner");
  let cls, icon, greetWord;
  if (hour >= 5 && hour < 12) { cls = "morning"; icon = "☀️"; greetWord = "Good morning"; }
  else if (hour >= 12 && hour < 17) { cls = "afternoon"; icon = "🌤️"; greetWord = "Good afternoon"; }
  else if (hour >= 17 && hour < 21) { cls = "evening"; icon = "🌇"; greetWord = "Good evening"; }
  else { cls = "night"; icon = "🌙"; greetWord = "Good night"; }
  banner.className = `greeting-banner ${cls}`;
  document.getElementById("greeting-title").textContent = `${greetWord}, ${name}! ${icon}`;
}

function updateGreetingSub(text) {
  document.getElementById("greeting-sub").textContent = text;
}

function setMascotDozing(isDozing) {
  document.getElementById("mini-mascot").classList.toggle("dozing", isDozing);
}

function setMascotMouth(happy) {
  const mouth = document.getElementById("mascot-mouth");
  if (mouth) mouth.setAttribute("d", happy ? "M76,124 Q100,150 124,124" : "M82,128 Q100,140 118,128");
}

function mascotWave() {
  const wrap = document.querySelector("#mini-mascot .mascot-wrap");
  if (!wrap) return;
  wrap.classList.add("wave");
  setMascotMouth(true);
  setTimeout(() => {
    wrap.classList.remove("wave");
    setMascotMouth(false);
  }, 1400);
}

/* ---------------- Progress rings ---------------- */

function setRing(el, progress, colorClass) {
  const p = Math.max(0, Math.min(1, progress));
  el.classList.remove("warn", "danger", "good");
  if (colorClass) el.classList.add(colorClass);
  el.style.strokeDashoffset = `${RING_CIRC * (1 - p)}`;
}

function updateEtaRing(etaMinutes) {
  const ring = document.getElementById("eta-ring");
  const MAX_ETA = 40;
  const progress = 1 - Math.min(etaMinutes / MAX_ETA, 1);
  const colorClass = etaMinutes <= 5 ? "good" : etaMinutes <= 20 ? "" : "warn";
  setRing(ring, progress, colorClass);
}

function updateCapacityRing(passengers, capacity) {
  const ring = document.getElementById("capacity-ring");
  const ratio = capacity ? passengers / capacity : 0;
  const colorClass = ratio >= 0.9 ? "danger" : ratio >= 0.7 ? "warn" : "good";
  setRing(ring, ratio, colorClass);
  document.getElementById("capacity-value").textContent = `${passengers}/${capacity}`;
  const seatsLeft = capacity - passengers;
  document.getElementById("capacity-label").textContent =
    seatsLeft <= 0 ? "Bus is full" : `${seatsLeft} seat${seatsLeft === 1 ? "" : "s"} available`;
}

/* ---------------- Confetti ---------------- */

function fireConfetti() {
  const layer = document.getElementById("confetti-layer");
  if (!layer) return;
  const colors = ["#4f46e5", "#0ea5e9", "#16a34a", "#eab308", "#ec4899"];
  for (let i = 0; i < 26; i++) {
    const piece = document.createElement("div");
    piece.className = "confetti-piece";
    piece.style.left = `${Math.random() * 100}%`;
    piece.style.background = colors[i % colors.length];
    piece.style.animationDelay = `${(Math.random() * 0.3).toFixed(2)}s`;
    piece.style.borderRadius = Math.random() > 0.5 ? "50%" : "2px";
    layer.appendChild(piece);
    setTimeout(() => piece.remove(), 1600);
  }
}

/* ---------------- Journey timeline ---------------- */

function renderTimeline() {
  const list = document.getElementById("journey-timeline");
  if (!routeStops.length) return;

  const fmtTime = (d) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const findNotifTime = (predicate) => {
    const n = lastNotifications.find(predicate);
    return n ? new Date(n.created_at) : null;
  };
  const startedAt = findNotifTime((n) => n.event_type === "bus_started");
  const collegeAt = findNotifTime((n) => n.event_type === "college_entry");
  const myArrivedAt = myAssignment
    ? findNotifTime((n) => n.event_type === "arrived_at_stop" && n.message.includes(myAssignment.stop_name))
    : null;

  const coveredKm = lastLoc ? lastLoc.distance_covered_km : 0;
  const currentStopId = lastLoc ? lastLoc.current_stop_id : null;

  list.innerHTML = routeStops.map((stop) => {
    const passed = stop.distance_from_start_km <= coveredKm;
    const isCurrent = lastLoc && stop.id === currentStopId && lastLoc.status !== "moving" && lastLoc.status !== "not_started";
    const isMine = myAssignment && stop.id === myAssignment.stop_id;

    let time = null;
    if (stop.sequence_order === 0) time = startedAt;
    if (isMine && myArrivedAt) time = myArrivedAt;
    if (stop.stop_name === "IFET College" && collegeAt) time = collegeAt;

    const stateClass = isCurrent ? "current" : passed ? "done" : "upcoming";
    const timeHtml = time ? `<span class="time">${fmtTime(time)}</span>` : "";
    const mineTag = isMine ? '<span class="mine-tag">You board here</span>' : "";

    return `<li class="${stateClass}"><span class="dot"></span><span class="stop-name">${stop.stop_name}</span>${mineTag}${timeHtml}</li>`;
  }).join("");
}

/* ---------------- Live map ---------------- */

function initMap(centerLat, centerLng) {
  map = L.map("live-map", { zoomControl: true, attributionControl: true }).setView([centerLat, centerLng], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map);
}

function busDivIcon(status) {
  return L.divIcon({
    className: "",
    html: `<div class="bus-pin ${status || ""}">🚌</div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

function stopDivIcon(passed) {
  return L.divIcon({
    className: "",
    html: `<div class="stop-pin ${passed ? "passed" : ""}"></div>`,
    iconSize: [12, 12],
    iconAnchor: [6, 6],
  });
}

function renderStopsOnMap() {
  if (!map || !routeStops.length) return;

  const latlngs = routeStops
    .filter((s) => s.latitude != null && s.longitude != null)
    .map((s) => [s.latitude, s.longitude]);

  if (latlngs.length) {
    L.polyline(latlngs, { color: "#4f46e5", weight: 4, opacity: 0.55, dashArray: "1,10", lineCap: "round" }).addTo(map);
    map.fitBounds(latlngs, { padding: [30, 30] });
  }

  routeStops.forEach((stop) => {
    if (stop.latitude == null || stop.longitude == null) return;
    const marker = L.marker([stop.latitude, stop.longitude], { icon: stopDivIcon(false) })
      .addTo(map)
      .bindPopup(`<strong>${stop.stop_name}</strong><br>${stop.distance_from_start_km} km from start`);
    stopMarkers[stop.id] = marker;
  });
}

function updateStopMarkers(coveredKm) {
  routeStops.forEach((stop) => {
    const marker = stopMarkers[stop.id];
    if (!marker) return;
    marker.setIcon(stopDivIcon(stop.distance_from_start_km <= coveredKm));
  });
}

function updateBusMarker(lat, lng, status, popupHtml) {
  if (lat == null || lng == null || !map) return;
  if (!busMarker) {
    busMarker = L.marker([lat, lng], { icon: busDivIcon(status), zIndexOffset: 1000 }).addTo(map);
  } else {
    busMarker.setLatLng([lat, lng]);
    busMarker.setIcon(busDivIcon(status));
  }
  if (popupHtml) busMarker.bindPopup(popupHtml);
}

/* ---------------- Profile / data ---------------- */

async function loadProfile() {
  const data = await api("/api/students/me");
  if (!data.success || !data.assignment) {
    const name = data.student ? data.student.name : "Student";
    document.getElementById("student-name").textContent = name;
    document.getElementById("assigned-bus").textContent = "No bus assigned";
    updateGreeting(name.split(" ")[0]);
    updateGreetingSub("You don't have a bus assignment yet - contact your Transport Officer.");
    return;
  }
  myAssignment = data.assignment;
  document.getElementById("student-name").textContent = data.student.name;
  document.getElementById("student-avatar").textContent = data.student.name.charAt(0).toUpperCase();
  document.getElementById("assigned-bus").textContent = data.assignment.bus_name;
  document.getElementById("assigned-stop").textContent = `Stop: ${data.assignment.stop_name}`;
  updateGreeting(data.student.name.split(" ")[0]);

  const routeData = await api(`/api/buses/${myAssignment.bus_id}/route`);
  routeStops = routeData.stops || [];

  const firstWithCoords = routeStops.find((s) => s.latitude != null && s.longitude != null);
  initMap(firstWithCoords ? firstWithCoords.latitude : 11.9, firstWithCoords ? firstWithCoords.longitude : 79.5);
  renderStopsOnMap();
  renderTimeline();
}

async function refreshLocationAndEta() {
  if (!myAssignment) return;
  try {
    const locData = await api(`/api/buses/${myAssignment.bus_id}/location`);
    if (!locData.success) return;
    const loc = locData.location;
    lastLoc = loc;

    const badge = document.getElementById("bus-status-badge");
    badge.textContent = loc.status.replace(/_/g, " ");
    badge.className = `badge ${loc.status}`;

    const trackingBadge = document.getElementById("tracking-mode-badge");
    trackingBadge.style.display = "inline-block";
    trackingBadge.textContent = loc.is_live ? "📡 LIVE GPS" : "Simulated";
    trackingBadge.className = `badge ${loc.is_live ? "low live-pulse" : "not_started"}`;

    const trafficLabel = document.getElementById("traffic-label");
    trafficLabel.innerHTML = `Traffic: <span class="badge ${loc.traffic_condition}">${loc.traffic_condition}</span>`;

    updateStopMarkers(loc.distance_covered_km);
    updateBusMarker(
      loc.lat, loc.lng, loc.status,
      `<strong>${loc.bus_name}</strong><br>${loc.status.replace(/_/g, " ")}<br>${loc.current_passengers}/${loc.capacity} on board`
    );

    document.getElementById("passenger-status").textContent = `${loc.current_passengers} / ${loc.capacity}`;
    updateCapacityRing(loc.current_passengers, loc.capacity);

    setMascotDozing(loc.status === "not_started");
    if (loc.status === "not_started") {
      updateGreetingSub(`${loc.bus_name} hasn't started its trip yet.`);
    } else if (loc.status === "reached_college") {
      updateGreetingSub(`${loc.bus_name} has reached IFET College. Journey complete!`);
    } else {
      updateGreetingSub(`${loc.bus_name} is ${loc.status.replace(/_/g, " ")} towards ${loc.next_stop_name || "the college"}.`);
    }

    if (loc.status === "arrived_at_stop" && loc.current_stop_id === myAssignment.stop_id) {
      if (!arrivalWaved) {
        arrivalWaved = true;
        mascotWave();
        updateGreetingSub(`${loc.bus_name} has arrived at your stop - ${myAssignment.stop_name}!`);
      }
    } else {
      arrivalWaved = false;
    }

    const etaData = await api(`/api/eta/predict?bus_id=${myAssignment.bus_id}&stop_id=${myAssignment.stop_id}`);
    if (etaData.success) {
      const etaMinutes = etaData.eta_minutes;
      document.getElementById("eta-value").textContent = etaMinutes === 0 ? "0" : `${etaMinutes}`;
      document.getElementById("eta-label").textContent =
        etaMinutes === 0 ? `Arrived at ${myAssignment.stop_name}` : `ETA to ${myAssignment.stop_name} (AI prototype)`;
      document.getElementById("distance-value").textContent = `${etaData.distance_km} km`;
      document.getElementById("stops-remaining-label").textContent = `${etaData.stops_remaining} stops remaining`;
      updateEtaRing(etaMinutes);
    }

    renderTimeline();
  } catch (e) { /* keep polling */ }
}

async function refreshNotifications() {
  const data = await api("/api/notifications");
  lastNotifications = data.notifications || [];
  const list = document.getElementById("notif-list");
  if (!lastNotifications.length) {
    list.innerHTML = '<li class="small-muted">No notifications yet.</li>';
  } else {
    list.innerHTML = lastNotifications
      .map((n) => `<li>${n.message}<span class="time">${new Date(n.created_at).toLocaleTimeString()}</span></li>`)
      .join("");
  }
  renderTimeline();
}

function showBoardingResult(success, message) {
  const box = document.getElementById("boarding-status");
  box.style.display = "block";
  box.className = `boarding-status ${success ? "success" : "error"}`;
  box.textContent = message;
  if (success) {
    playBeep();
    fireConfetti();
    mascotWave();
    refreshLocationAndEta();
  }
}

async function submitBoarding(qrText) {
  const data = await api("/api/boarding", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ qr_text: qrText }),
  });
  showBoardingResult(data.success, data.message);
}

document.getElementById("qr-manual-submit").addEventListener("click", () => {
  const val = document.getElementById("qr-manual-input").value.trim();
  if (val) submitBoarding(val);
});

document.getElementById("start-scan-btn").addEventListener("click", async () => {
  if (html5QrCode) return;
  html5QrCode = new Html5Qrcode("qr-reader");
  try {
    await html5QrCode.start(
      { facingMode: "environment" },
      { fps: 10, qrbox: 220 },
      async (decodedText) => {
        await html5QrCode.stop();
        html5QrCode.clear();
        html5QrCode = null;
        submitBoarding(decodedText);
      },
      () => {}
    );
  } catch (err) {
    showBoardingResult(false, "Camera unavailable in this environment. Use the text field below (demo fallback mode).");
    html5QrCode = null;
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  navigateTo("index.html");
});

(async function init() {
  await loadProfile();
  refreshLocationAndEta();
  refreshNotifications();
  setInterval(refreshLocationAndEta, 3000);
  setInterval(refreshNotifications, 5000);
})();
