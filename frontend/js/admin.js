const API = "";

let lookup = { buses: [], routes: [], stops: [] };
let editingBusId = null;
let editingStudentId = null;
let editingDriverId = null;

let fleetMap = null;
let fleetMarkers = {};
let fleetInitialized = false;

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, { credentials: "include", ...options });
  if (res.status === 401) {
    window.location.href = "index.html";
    throw new Error("Not logged in");
  }
  return res.json();
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function showAlert(elId, success, message) {
  const box = document.getElementById(elId);
  box.textContent = message;
  box.className = `alert show ${success ? "success" : "error"}`;
  setTimeout(() => box.classList.remove("show"), 4000);
}

/* ---------------- Tabs ---------------- */

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "map") {
      if (!fleetInitialized) initFleetMap();
      setTimeout(() => fleetMap && fleetMap.invalidateSize(), 50);
    }
  });
});

/* ---------------- Session / overview ---------------- */

async function loadSession() {
  const data = await api("/api/session");
  const label = data.role === "admin" ? "Transport Officer" : "Admin";
  document.getElementById("admin-name").textContent = label;
  document.getElementById("admin-avatar").textContent = label.charAt(0);
}

async function startBus(busId) {
  await api(`/api/buses/${busId}/start`, { method: "POST" });
  refreshBuses();
}

async function refreshBuses() {
  const data = await api("/api/buses");
  const buses = data.buses || [];

  document.getElementById("total-buses").textContent = buses.length;
  const active = buses.filter((b) => ["moving", "waiting", "arrived_at_stop"].includes(b.status)).length;
  document.getElementById("active-buses").textContent = active;
  document.getElementById("total-passengers").textContent =
    buses.reduce((sum, b) => sum + (b.current_passengers || 0), 0);
  document.getElementById("college-entries").textContent =
    buses.filter((b) => b.college_entry_detected).length;

  const tbody = document.getElementById("buses-table-body");
  tbody.innerHTML = buses.map((b) => `
    <tr>
      <td>${escapeHtml(b.bus_name)}</td>
      <td>${b.is_live
          ? '<span class="badge low">📡 LIVE GPS</span>'
          : '<span class="badge not_started">Simulated</span>'}</td>
      <td><span class="badge ${b.status}">${(b.status || "").replace(/_/g, " ")}</span></td>
      <td>${escapeHtml(b.current_stop_name) || "-"}</td>
      <td>${escapeHtml(b.next_stop_name) || "-"}</td>
      <td><span class="badge ${b.traffic_condition}">${b.traffic_condition || "-"}</span></td>
      <td>${b.current_passengers} / ${b.capacity}</td>
      <td>${b.college_entry_detected ? "Entered" : "Not yet"}</td>
      <td>${b.status === "not_started"
          ? `<button class="btn secondary sm" onclick="startBus(${b.id})">Start</button>`
          : "-"}</td>
    </tr>
  `).join("");

  if (fleetMap) updateFleetMarkers(buses);
}

async function refreshAttendance() {
  const data = await api("/api/attendance");
  const rows = data.attendance || [];
  document.getElementById("attendance-table-body").innerHTML = rows.length
    ? rows.map((a) => `
        <tr>
          <td>${escapeHtml(a.student_name)}</td><td>${escapeHtml(a.bus_name)}</td><td>${escapeHtml(a.stop_name)}</td>
          <td>${a.attendance_time}</td>
        </tr>`).join("")
    : '<tr><td colspan="4" class="small-muted">No boardings recorded yet today.</td></tr>';
}

async function refreshRouteOptimization() {
  const data = await api("/api/route-optimize?bus_id=1");
  if (!data.success) return;
  document.getElementById("route-opt-summary").textContent =
    `Total optimized time: ${data.total_estimated_minutes} min (Dijkstra shortest-path over alternate road segments)`;
  document.getElementById("route-opt-body").innerHTML = data.optimized_path.map((seg) => `
    <tr><td>${escapeHtml(seg.from)}</td><td>${escapeHtml(seg.to)}</td><td>${escapeHtml(seg.road)}</td><td>${seg.minutes}</td></tr>
  `).join("");
}

async function refreshNotifications() {
  const data = await api("/api/notifications");
  const list = document.getElementById("notif-list");
  if (!data.notifications || data.notifications.length === 0) {
    list.innerHTML = '<li class="small-muted">No notifications yet.</li>';
    return;
  }
  list.innerHTML = data.notifications
    .map((n) => `<li>${escapeHtml(n.message)}<span class="time">${new Date(n.created_at).toLocaleTimeString()}</span></li>`)
    .join("");
}

/* ---------------- Fleet map ---------------- */

function busDivIcon(status) {
  return L.divIcon({
    className: "",
    html: `<div class="bus-pin ${status || ""}">🚌</div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

function initFleetMap() {
  fleetInitialized = true;
  const stopsWithCoords = lookup.stops.filter((s) => s.latitude != null && s.longitude != null);
  const center = stopsWithCoords.length ? [stopsWithCoords[0].latitude, stopsWithCoords[0].longitude] : [11.9, 79.5];

  fleetMap = L.map("fleet-map").setView(center, 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(fleetMap);

  if (stopsWithCoords.length) {
    const latlngs = stopsWithCoords.map((s) => [s.latitude, s.longitude]);
    L.polyline(latlngs, { color: "#4f46e5", weight: 4, opacity: 0.4, dashArray: "1,10" }).addTo(fleetMap);
    stopsWithCoords.forEach((s) => {
      L.circleMarker([s.latitude, s.longitude], { radius: 5, color: "#6b7280", fillColor: "#fff", fillOpacity: 1, weight: 2 })
        .addTo(fleetMap)
        .bindPopup(`<strong>${escapeHtml(s.stop_name)}</strong>`);
    });
    fleetMap.fitBounds(latlngs, { padding: [30, 30] });
  }

  refreshBuses();
}

function updateFleetMarkers(buses) {
  buses.forEach((b) => {
    if (b.lat == null || b.lng == null) return;
    const popupHtml = `<strong>${escapeHtml(b.bus_name)}</strong> ${b.is_live ? "📡 live" : "(simulated)"}<br>${(b.status || "").replace(/_/g, " ")}<br>${b.current_passengers}/${b.capacity} on board`;
    if (!fleetMarkers[b.id]) {
      fleetMarkers[b.id] = L.marker([b.lat, b.lng], { icon: busDivIcon(b.status) }).addTo(fleetMap).bindPopup(popupHtml);
    } else {
      fleetMarkers[b.id].setLatLng([b.lat, b.lng]);
      fleetMarkers[b.id].setIcon(busDivIcon(b.status));
      fleetMarkers[b.id].setPopupContent(popupHtml);
    }
  });
}

/* ---------------- Lookup data (for dropdowns) ---------------- */

async function loadLookup() {
  const data = await api("/api/admin/lookup");
  lookup = { buses: data.buses || [], routes: data.routes || [], stops: data.stops || [] };

  const routeSelect = document.getElementById("bus-route");
  routeSelect.innerHTML = lookup.routes.map((r) => `<option value="${r.id}">${escapeHtml(r.route_name)}</option>`).join("");

  const busSelect = document.getElementById("student-bus");
  busSelect.innerHTML = lookup.buses.map((b) => `<option value="${b.id}">${escapeHtml(b.bus_name)}</option>`).join("");
  populateStopsForSelectedBus();

  const driverBusSelect = document.getElementById("driver-bus");
  driverBusSelect.innerHTML = '<option value="">Unassigned</option>' +
    lookup.buses.map((b) => `<option value="${b.id}">${escapeHtml(b.bus_name)}</option>`).join("");
}

function populateStopsForSelectedBus(selectedStopId) {
  const busId = parseInt(document.getElementById("student-bus").value, 10);
  const bus = lookup.buses.find((b) => b.id === busId);
  const stopSelect = document.getElementById("student-stop");
  const stops = bus ? lookup.stops.filter((s) => s.route_id === bus.route_id) : lookup.stops;
  stopSelect.innerHTML = stops
    .map((s) => `<option value="${s.id}" ${s.id === selectedStopId ? "selected" : ""}>${escapeHtml(s.stop_name)}</option>`)
    .join("");
}

/* ---------------- Manage: Buses ---------------- */

async function refreshManageBuses() {
  const data = await api("/api/buses");
  const buses = data.buses || [];
  document.getElementById("manage-buses-body").innerHTML = buses.map((b) => `
    <tr>
      <td>${escapeHtml(b.bus_name)}</td>
      <td>${escapeHtml(b.driver_name) || "-"}</td>
      <td>${b.capacity}</td>
      <td><span class="badge ${b.status}">${(b.status || "").replace(/_/g, " ")}</span></td>
      <td>
        <button class="btn ghost sm" onclick='editBus(${JSON.stringify(b).replace(/'/g, "&apos;")})'>Edit</button>
        <button class="btn danger sm" onclick="deleteBus(${b.id})">Delete</button>
      </td>
    </tr>
  `).join("");
}

function editBus(bus) {
  editingBusId = bus.id;
  document.getElementById("bus-form-title").textContent = `Edit Bus: ${bus.bus_name}`;
  document.getElementById("bus-name").value = bus.bus_name;
  document.getElementById("bus-driver").value = bus.driver_name || "";
  document.getElementById("bus-capacity").value = bus.capacity;
  document.getElementById("bus-route").value = bus.route_id;
  document.getElementById("bus-submit-btn").textContent = "Save Changes";
  document.getElementById("bus-cancel-btn").style.display = "inline-flex";
  document.getElementById("bus-form").scrollIntoView({ behavior: "smooth", block: "center" });
}

function cancelBusEdit() {
  editingBusId = null;
  document.getElementById("bus-form").reset();
  document.getElementById("bus-form-title").textContent = "Add a Bus";
  document.getElementById("bus-submit-btn").textContent = "Add Bus";
  document.getElementById("bus-cancel-btn").style.display = "none";
}

async function deleteBus(id) {
  if (!confirm("Delete this bus? This also removes its attendance history and student assignments.")) return;
  const data = await api(`/api/admin/buses/${id}`, { method: "DELETE" });
  if (data.success) {
    showAlert("bus-alert", true, "Bus deleted.");
    refreshManageBuses();
    refreshBuses();
    loadLookup();
  } else {
    showAlert("bus-alert", false, data.message || "Could not delete bus.");
  }
}

document.getElementById("bus-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    bus_name: document.getElementById("bus-name").value.trim(),
    driver_name: document.getElementById("bus-driver").value.trim(),
    capacity: parseInt(document.getElementById("bus-capacity").value, 10),
    route_id: parseInt(document.getElementById("bus-route").value, 10),
  };
  const data = editingBusId
    ? await api(`/api/admin/buses/${editingBusId}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
    : await api("/api/admin/buses", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });

  if (data.success) {
    showAlert("bus-alert", true, editingBusId ? "Bus updated." : "Bus added.");
    cancelBusEdit();
    refreshManageBuses();
    refreshBuses();
    loadLookup();
  } else {
    showAlert("bus-alert", false, data.message || "Something went wrong.");
  }
});

document.getElementById("bus-cancel-btn").addEventListener("click", cancelBusEdit);

/* ---------------- Manage: Students ---------------- */

async function refreshManageStudents() {
  const data = await api("/api/students");
  const students = data.students || [];
  document.getElementById("manage-students-body").innerHTML = students.map((s) => `
    <tr>
      <td>${escapeHtml(s.username)}</td>
      <td>${escapeHtml(s.name)}</td>
      <td>${escapeHtml(s.register_no) || "-"}</td>
      <td>${escapeHtml(s.bus_name) || "Unassigned"}</td>
      <td>${escapeHtml(s.stop_name) || "-"}</td>
      <td>
        <button class="btn ghost sm" onclick='editStudent(${JSON.stringify(s).replace(/'/g, "&apos;")})'>Edit</button>
        <button class="btn danger sm" onclick="deleteStudent(${s.id})">Delete</button>
      </td>
    </tr>
  `).join("");
}

function editStudent(student) {
  editingStudentId = student.id;
  document.getElementById("student-form-title").textContent = `Edit Student: ${student.name}`;
  document.getElementById("student-username").value = student.username;
  document.getElementById("student-username").disabled = true;
  document.getElementById("student-password").placeholder = "Leave blank to keep unchanged";
  document.getElementById("student-name-input").value = student.name;
  document.getElementById("student-regno").value = student.register_no || "";
  document.getElementById("student-phone").value = student.phone || "";
  if (student.bus_id) document.getElementById("student-bus").value = student.bus_id;
  populateStopsForSelectedBus(student.stop_id);
  document.getElementById("student-submit-btn").textContent = "Save Changes";
  document.getElementById("student-cancel-btn").style.display = "inline-flex";
  document.getElementById("student-form").scrollIntoView({ behavior: "smooth", block: "center" });
}

function cancelStudentEdit() {
  editingStudentId = null;
  document.getElementById("student-form").reset();
  document.getElementById("student-username").disabled = false;
  document.getElementById("student-password").placeholder = "Required when creating";
  document.getElementById("student-form-title").textContent = "Add a Student";
  document.getElementById("student-submit-btn").textContent = "Add Student";
  document.getElementById("student-cancel-btn").style.display = "none";
  populateStopsForSelectedBus();
}

async function deleteStudent(id) {
  if (!confirm("Delete this student? This also removes their attendance history.")) return;
  const data = await api(`/api/admin/students/${id}`, { method: "DELETE" });
  if (data.success) {
    showAlert("student-alert", true, "Student deleted.");
    refreshManageStudents();
  } else {
    showAlert("student-alert", false, data.message || "Could not delete student.");
  }
}

document.getElementById("student-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const password = document.getElementById("student-password").value;
  const payload = {
    username: document.getElementById("student-username").value.trim(),
    name: document.getElementById("student-name-input").value.trim(),
    register_no: document.getElementById("student-regno").value.trim(),
    phone: document.getElementById("student-phone").value.trim(),
    bus_id: parseInt(document.getElementById("student-bus").value, 10) || null,
    stop_id: parseInt(document.getElementById("student-stop").value, 10) || null,
  };
  if (password) payload.password = password;

  if (!editingStudentId && !password) {
    showAlert("student-alert", false, "Password is required when creating a new student.");
    return;
  }

  const data = editingStudentId
    ? await api(`/api/admin/students/${editingStudentId}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
    : await api("/api/admin/students", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });

  if (data.success) {
    showAlert("student-alert", true, editingStudentId ? "Student updated." : "Student added.");
    cancelStudentEdit();
    refreshManageStudents();
  } else {
    showAlert("student-alert", false, data.message || "Something went wrong.");
  }
});

document.getElementById("student-cancel-btn").addEventListener("click", cancelStudentEdit);

/* ---------------- Manage: Admins ---------------- */

async function refreshManageAdmins() {
  const data = await api("/api/admin/admins");
  const admins = data.admins || [];
  document.getElementById("manage-admins-body").innerHTML = admins.map((a) => `
    <tr>
      <td>${escapeHtml(a.username)}</td>
      <td>${escapeHtml(a.name)}</td>
      <td><button class="btn danger sm" onclick="deleteAdmin(${a.id})">Delete</button></td>
    </tr>
  `).join("");
}

async function deleteAdmin(id) {
  if (!confirm("Delete this admin account?")) return;
  const data = await api(`/api/admin/admins/${id}`, { method: "DELETE" });
  if (data.success) {
    showAlert("admin-form-alert", true, "Admin deleted.");
    refreshManageAdmins();
  } else {
    showAlert("admin-form-alert", false, data.message || "Could not delete admin.");
  }
}

document.getElementById("admin-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    username: document.getElementById("admin-username").value.trim(),
    password: document.getElementById("admin-password").value,
    name: document.getElementById("admin-name-input").value.trim(),
  };
  const data = await api("/api/admin/admins", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (data.success) {
    showAlert("admin-form-alert", true, "Admin added.");
    document.getElementById("admin-form").reset();
    refreshManageAdmins();
  } else {
    showAlert("admin-form-alert", false, data.message || "Something went wrong.");
  }
});

/* ---------------- Manage: Drivers ---------------- */

async function refreshManageDrivers() {
  const data = await api("/api/admin/drivers");
  const drivers = data.drivers || [];
  document.getElementById("manage-drivers-body").innerHTML = drivers.map((d) => `
    <tr>
      <td>${escapeHtml(d.username)}</td>
      <td>${escapeHtml(d.name)}</td>
      <td>${escapeHtml(d.phone) || "-"}</td>
      <td>${escapeHtml(d.license_no) || "-"}</td>
      <td>${escapeHtml(d.bus_name) || "Unassigned"}</td>
      <td>
        <button class="btn ghost sm" onclick='editDriver(${JSON.stringify(d).replace(/'/g, "&apos;")})'>Edit</button>
        <button class="btn danger sm" onclick="deleteDriver(${d.id})">Delete</button>
      </td>
    </tr>
  `).join("");
}

function editDriver(driver) {
  editingDriverId = driver.id;
  document.getElementById("driver-username").value = driver.username;
  document.getElementById("driver-username").disabled = true;
  document.getElementById("driver-password").placeholder = "Leave blank to keep unchanged";
  document.getElementById("driver-name-input").value = driver.name;
  document.getElementById("driver-phone").value = driver.phone || "";
  document.getElementById("driver-license").value = driver.license_no || "";
  document.getElementById("driver-bus").value = driver.bus_id || "";
  document.getElementById("driver-submit-btn").textContent = "Save Changes";
  document.getElementById("driver-cancel-btn").style.display = "inline-flex";
  document.getElementById("driver-form").scrollIntoView({ behavior: "smooth", block: "center" });
}

function cancelDriverEdit() {
  editingDriverId = null;
  document.getElementById("driver-form").reset();
  document.getElementById("driver-username").disabled = false;
  document.getElementById("driver-password").placeholder = "Required when creating";
  document.getElementById("driver-submit-btn").textContent = "Add Driver";
  document.getElementById("driver-cancel-btn").style.display = "none";
}

async function deleteDriver(id) {
  if (!confirm("Delete this driver account?")) return;
  const data = await api(`/api/admin/drivers/${id}`, { method: "DELETE" });
  if (data.success) {
    showAlert("driver-form-alert", true, "Driver deleted.");
    refreshManageDrivers();
  } else {
    showAlert("driver-form-alert", false, data.message || "Could not delete driver.");
  }
}

document.getElementById("driver-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const password = document.getElementById("driver-password").value;
  const payload = {
    username: document.getElementById("driver-username").value.trim(),
    name: document.getElementById("driver-name-input").value.trim(),
    phone: document.getElementById("driver-phone").value.trim(),
    license_no: document.getElementById("driver-license").value.trim(),
    bus_id: parseInt(document.getElementById("driver-bus").value, 10) || null,
  };
  if (password) payload.password = password;

  if (!editingDriverId && !password) {
    showAlert("driver-form-alert", false, "Password is required when creating a new driver.");
    return;
  }

  const data = editingDriverId
    ? await api(`/api/admin/drivers/${editingDriverId}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
    : await api("/api/admin/drivers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });

  if (data.success) {
    showAlert("driver-form-alert", true, editingDriverId ? "Driver updated." : "Driver added.");
    cancelDriverEdit();
    refreshManageDrivers();
  } else {
    showAlert("driver-form-alert", false, data.message || "Something went wrong.");
  }
});

document.getElementById("driver-cancel-btn").addEventListener("click", cancelDriverEdit);

/* ---------------- Logout / init ---------------- */

document.getElementById("student-bus").addEventListener("change", () => populateStopsForSelectedBus());

document.getElementById("logout-btn").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  window.location.href = "index.html";
});

(async function init() {
  await loadSession();
  await loadLookup();
  refreshBuses();
  refreshManageBuses();
  refreshManageStudents();
  refreshManageDrivers();
  refreshManageAdmins();
  refreshAttendance();
  refreshRouteOptimization();
  refreshNotifications();

  setInterval(refreshBuses, 3000);
  setInterval(refreshAttendance, 4000);
  setInterval(refreshRouteOptimization, 8000);
  setInterval(refreshNotifications, 5000);
})();
