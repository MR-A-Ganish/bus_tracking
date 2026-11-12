const API = "";
let watchId = null;
let heartbeat = null;
let tripId = null;
let assignedBusId = null;
let sending = false;
let acquiring = false;
let generation = 0;
let lastSentAt = 0;
let lastAcceptedAt = 0;
let pingCount = 0;
let map = null;
let myMarker = null;
let busy = false;

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    credentials: "include", signal: AbortSignal.timeout(15000), ...options
  });
  if (response.status === 401) {
    window.location.href = "index.html";
    throw new Error("Please sign in again");
  }
  const data = await response.json();
  if (!response.ok || !data.success) {
    const error = new Error(data.message || "Request failed");
    error.status = response.status;
    error.code = data.error_code;
    throw error;
  }
  return data;
}

function showAlert(success, message) {
  const box = document.getElementById("driver-alert");
  box.textContent = message;
  box.className = `alert show ${success ? "success" : "error"}`;
}

function gpsStatus(message, live = false) {
  const badge = document.getElementById("gps-status-badge");
  badge.textContent = message;
  badge.className = `badge ${live ? "moving" : "not_started"}`;
}

function updateMyMarker(latitude, longitude) {
  if (!window.L) return;
  if (!map) {
    map = L.map("driver-map").setView([latitude, longitude], 15);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);
  }
  if (!myMarker) myMarker = L.marker([latitude, longitude]).addTo(map);
  myMarker.setLatLng([latitude, longitude]);
  map.panTo([latitude, longitude]);
}

function refreshQr() {
  const image = document.getElementById("boarding-qr");
  image.hidden = !tripId || !assignedBusId;
  if (!image.hidden) image.src = `/api/buses/${assignedBusId}/qr?t=${Date.now()}`;
}

async function loadProfile() {
  const { driver } = await api("/api/driver/me");
  document.getElementById("driver-name").textContent = driver.name;
  document.getElementById("driver-avatar").textContent = driver.name.charAt(0).toUpperCase();
  assignedBusId = driver.bus_id;
  tripId = driver.active_trip_id;
  document.getElementById("driver-bus-name").textContent = driver.bus_name || "No bus assigned";
  document.getElementById("driver-bus-route").textContent = driver.route_id ? `Route #${driver.route_id}` : "Contact management";
  document.getElementById("start-trip-btn").disabled = !driver.bus_id;
  document.getElementById("start-trip-btn").textContent = tripId ? "Resume location sharing" : "Start trip";
  document.getElementById("end-trip-btn").style.display = tripId ? "inline-flex" : "none";
  refreshQr();
}

async function sendLocation(position, token) {
  if (token !== generation || watchId === null || sending || Date.now() - lastSentAt < 4000) return;
  if (Date.now() - position.timestamp > 30000) return;
  sending = true;
  const { latitude, longitude, accuracy, speed } = position.coords;
  document.getElementById("gps-accuracy-label").textContent = `Accuracy +/-${Math.round(accuracy)} m`;
  updateMyMarker(latitude, longitude);
  try {
    await api("/api/driver/location", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ latitude, longitude, accuracy_m: accuracy,
        speed_kmph: speed == null ? 0 : speed * 3.6,
        recorded_at: new Date(position.timestamp).toISOString(), trip_id: tripId })
    });
    lastSentAt = Date.now();
    lastAcceptedAt = lastSentAt;
    pingCount += 1;
    document.getElementById("last-ping-value").textContent = new Date().toLocaleTimeString();
    document.getElementById("ping-count-label").textContent = `${pingCount} updates shared`;
    if (token === generation) {
      gpsStatus("Live GPS", true);
      document.getElementById("driver-alert").className = "alert";
    }
  } catch (error) {
    if (error.code === "trip_changed") {
      generation += 1;
      navigator.geolocation.clearWatch(watchId);
      watchId = null;
      clearInterval(heartbeat);
      document.getElementById("start-trip-btn").style.display = "inline-flex";
      await loadProfile();
    }
    gpsStatus("Update failed");
    showAlert(false, `${error.message}. Retrying with the next GPS fix.`);
  } finally {
    sending = false;
  }
}

function handleGeoError(error) {
  gpsStatus("GPS unavailable");
  showAlert(false, `${error.message}. Check location permission, signal and network connection.`);
}

async function startSharing() {
  if (busy || watchId !== null) return;
  if (!window.isSecureContext || !navigator.geolocation) {
    showAlert(false, "Phone GPS requires HTTPS and a location-capable browser.");
    return;
  }
  busy = true;
  document.getElementById("start-trip-btn").disabled = true;
  try {
    const result = await api("/api/driver/start-trip", { method: "POST" });
    tripId = result.trip_id;
    const token = ++generation;
    gpsStatus("Waiting for GPS");
    watchId = navigator.geolocation.watchPosition(position => sendLocation(position, token), handleGeoError,
      { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 });
    heartbeat = setInterval(() => {
      if (acquiring || token !== generation) return;
      acquiring = true;
      navigator.geolocation.getCurrentPosition(position => {
        acquiring = false;
        sendLocation(position, token);
      }, error => {
        acquiring = false;
        if (token === generation) handleGeoError(error);
      }, { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 });
    }, 10000);
    document.getElementById("start-trip-btn").style.display = "none";
    document.getElementById("end-trip-btn").style.display = "inline-flex";
    document.getElementById("trip-help-text").textContent = "Keep this page visible and your screen on. Assigned students and management receive accepted GPS updates.";
    refreshQr();
  } catch (error) {
    showAlert(false, error.message);
  } finally {
    busy = false;
    document.getElementById("start-trip-btn").disabled = false;
  }
}

async function endTrip() {
  generation += 1;
  if (watchId !== null) navigator.geolocation.clearWatch(watchId);
  watchId = null;
  clearInterval(heartbeat);
  while (sending) await new Promise(resolve => setTimeout(resolve, 50));
  if (tripId) await api("/api/driver/end-trip", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trip_id: tripId })
  });
  tripId = null;
  gpsStatus("Sharing stopped");
  document.getElementById("start-trip-btn").textContent = "Start trip";
  document.getElementById("start-trip-btn").style.display = "inline-flex";
  document.getElementById("end-trip-btn").style.display = "none";
  refreshQr();
  showAlert(true, "Trip ended. The map retains your last known GPS location.");
}

document.getElementById("start-trip-btn").addEventListener("click", startSharing);
document.getElementById("end-trip-btn").addEventListener("click", async () => {
  if (busy) return;
  busy = true;
  try { await endTrip(); } catch (error) { showAlert(false, error.message); }
  finally { busy = false; }
});
document.getElementById("logout-btn").addEventListener("click", async () => {
  if (busy) return;
  busy = true;
  try {
    await endTrip();
    await api("/api/logout", { method: "POST" });
    window.location.href = "index.html";
  } catch (error) { showAlert(false, error.message); }
  finally { busy = false; }
});
setInterval(() => {
  if (watchId !== null && Date.now() - lastAcceptedAt > 30000) gpsStatus("Waiting for a fresh update");
}, 5000);
setInterval(refreshQr, 60000);
loadProfile().catch(error => showAlert(false, error.message));
