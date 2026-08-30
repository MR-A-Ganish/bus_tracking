const API = "";
let watchId = null;
let pingCount = 0;
let lastSendTime = 0;
const MIN_SEND_INTERVAL_MS = 3000;

let map = null;
let myMarker = null;

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, { credentials: "include", ...options });
  if (res.status === 401) {
    window.location.href = "index.html";
    throw new Error("Not logged in");
  }
  return res.json();
}

function showAlert(success, message) {
  const box = document.getElementById("driver-alert");
  box.textContent = message;
  box.className = `alert show ${success ? "success" : "error"}`;
}

function initMap(lat, lng) {
  map = L.map("driver-map").setView([lat, lng], 14);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map);
}

function updateMyMarker(lat, lng) {
  if (!map) initMap(lat, lng);
  const icon = L.divIcon({ className: "", html: '<div class="bus-pin moving">🚌</div>', iconSize: [30, 30], iconAnchor: [15, 15] });
  if (!myMarker) {
    myMarker = L.marker([lat, lng], { icon }).addTo(map);
  } else {
    myMarker.setLatLng([lat, lng]);
  }
  map.panTo([lat, lng]);
}

async function loadProfile() {
  const data = await api("/api/driver/me");
  if (!data.success || !data.driver) {
    document.getElementById("driver-name").textContent = "Driver";
    return;
  }
  const driver = data.driver;
  document.getElementById("driver-name").textContent = driver.name;
  document.getElementById("driver-avatar").textContent = driver.name.charAt(0).toUpperCase();

  if (!driver.bus_id) {
    document.getElementById("driver-bus-name").textContent = "No bus assigned";
    document.getElementById("start-trip-btn").disabled = true;
    showAlert(false, "You don't have a bus assigned yet - contact your Transport Officer.");
    return;
  }
  document.getElementById("driver-bus-name").textContent = driver.bus_name;
  document.getElementById("driver-bus-route").textContent = `Route #${driver.route_id}`;
}

function sendLocation(position) {
  const { latitude, longitude, accuracy, speed } = position.coords;

  document.getElementById("gps-accuracy-label").textContent = `Accuracy: ±${Math.round(accuracy)} m`;
  updateMyMarker(latitude, longitude);

  const now = Date.now();
  if (now - lastSendTime < MIN_SEND_INTERVAL_MS) return;
  lastSendTime = now;

  api("/api/driver/location", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lat: latitude, lng: longitude, accuracy, speed }),
  }).then((data) => {
    if (data.success) {
      pingCount += 1;
      document.getElementById("ping-count-label").textContent = `${pingCount} update${pingCount === 1 ? "" : "s"} sent`;
      document.getElementById("last-ping-value").textContent = new Date().toLocaleTimeString();
    }
  });
}

function handleGeoError(err) {
  const messages = {
    1: "Location permission denied. Allow location access in your browser settings to share GPS.",
    2: "Location unavailable - check your device's GPS/network signal.",
    3: "Location request timed out - trying again.",
  };
  showAlert(false, messages[err.code] || "Could not get your location.");
}

document.getElementById("start-trip-btn").addEventListener("click", async () => {
  if (!("geolocation" in navigator)) {
    showAlert(false, "This browser doesn't support location sharing.");
    return;
  }

  const data = await api("/api/driver/start-trip", { method: "POST" });
  if (!data.success) {
    showAlert(false, data.message || "Could not start the trip.");
    return;
  }

  watchId = navigator.geolocation.watchPosition(sendLocation, handleGeoError, {
    enableHighAccuracy: true,
    maximumAge: 5000,
    timeout: 15000,
  });

  document.getElementById("start-trip-btn").style.display = "none";
  document.getElementById("end-trip-btn").style.display = "inline-flex";
  document.getElementById("gps-status-badge").textContent = "live";
  document.getElementById("gps-status-badge").className = "badge moving";
  document.getElementById("trip-help-text").textContent =
    "Sharing your real live location. Students and the Management dashboard can now see this bus move in real time.";
  showAlert(true, "Trip started - sharing live GPS.");
});

document.getElementById("end-trip-btn").addEventListener("click", async () => {
  if (watchId !== null) {
    navigator.geolocation.clearWatch(watchId);
    watchId = null;
  }
  await api("/api/driver/end-trip", { method: "POST" });

  document.getElementById("start-trip-btn").style.display = "inline-flex";
  document.getElementById("end-trip-btn").style.display = "none";
  document.getElementById("gps-status-badge").textContent = "not sharing";
  document.getElementById("gps-status-badge").className = "badge not_started";
  document.getElementById("trip-help-text").textContent =
    "Press Start Trip to switch this bus to real live tracking.";
  showAlert(true, "Trip ended. The bus will fall back to normal tracking.");
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  if (watchId !== null) navigator.geolocation.clearWatch(watchId);
  await api("/api/logout", { method: "POST" });
  window.location.href = "index.html";
});

loadProfile();
