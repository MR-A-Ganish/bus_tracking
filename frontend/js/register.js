const API = "";
let lookup = { buses: [], stops: [] };

const usernameInput = document.getElementById("reg-username");
const passwordInput = document.getElementById("reg-password");
const mascot = initMascot({ usernameInput, passwordInput });

document.getElementById("toggle-reg-password").addEventListener("click", (e) => {
  const showing = passwordInput.type === "text";
  passwordInput.type = showing ? "password" : "text";
  e.currentTarget.textContent = showing ? "👁️" : "🙈";
  e.currentTarget.setAttribute("aria-label", showing ? "Show password" : "Hide password");
});

function showAlert(success, message) {
  const box = document.getElementById("register-alert");
  box.textContent = message;
  box.className = `alert show ${success ? "success" : "error"}`;
}

async function loadLookup() {
  const res = await fetch(`${API}/api/register/lookup`);
  const data = await res.json();
  lookup = { buses: data.buses || [], stops: data.stops || [] };

  const busSelect = document.getElementById("reg-bus");
  busSelect.innerHTML = lookup.buses.map((b) => `<option value="${b.id}">${b.bus_name}</option>`).join("");
  busSelect.addEventListener("change", populateStops);
  populateStops();
}

function populateStops() {
  const busId = parseInt(document.getElementById("reg-bus").value, 10);
  const bus = lookup.buses.find((b) => b.id === busId);
  const stopSelect = document.getElementById("reg-stop");
  const stops = bus ? lookup.stops.filter((s) => s.route_id === bus.route_id) : lookup.stops;
  stopSelect.innerHTML = stops.map((s) => `<option value="${s.id}">${s.stop_name}</option>`).join("");
}

document.getElementById("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorBox = document.getElementById("error-msg");
  const submitBtn = document.getElementById("register-submit");
  errorBox.style.display = "none";
  submitBtn.classList.add("loading");

  const payload = {
    username: usernameInput.value.trim(),
    password: passwordInput.value,
    name: document.getElementById("reg-name").value.trim(),
    register_no: document.getElementById("reg-regno").value.trim(),
    phone: document.getElementById("reg-phone").value.trim(),
    bus_id: parseInt(document.getElementById("reg-bus").value, 10) || null,
    stop_id: parseInt(document.getElementById("reg-stop").value, 10) || null,
  };

  try {
    const res = await fetch(`${API}/api/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!data.success) {
      submitBtn.classList.remove("loading");
      mascot.sad();
      errorBox.textContent = data.message || "Registration failed";
      errorBox.style.display = "block";
      return;
    }

    mascot.happy();
    setTimeout(() => { window.location.href = "student.html"; }, 500);
  } catch (err) {
    submitBtn.classList.remove("loading");
    mascot.sad();
    errorBox.textContent = "Could not reach the server. Is the Flask backend running?";
    errorBox.style.display = "block";
  }
});

loadLookup();
