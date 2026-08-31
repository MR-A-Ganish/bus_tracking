const API = "";

const usernameInput = document.getElementById("username");
const passwordInput = document.getElementById("password");
const mascot = initMascot({ usernameInput, passwordInput });

document.getElementById("toggle-password").addEventListener("click", (e) => {
  const showing = passwordInput.type === "text";
  passwordInput.type = showing ? "password" : "text";
  e.currentTarget.textContent = showing ? "👁️" : "🙈";
  e.currentTarget.setAttribute("aria-label", showing ? "Show password" : "Hide password");
});

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  const errorBox = document.getElementById("error-msg");
  const submitBtn = document.getElementById("login-submit");
  errorBox.style.display = "none";
  submitBtn.classList.add("loading");

  try {
    const res = await fetch(`${API}/api/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();

    if (!data.success) {
      submitBtn.classList.remove("loading");
      mascot.sad();
      errorBox.textContent = data.message || "Login failed";
      errorBox.style.display = "block";
      return;
    }

    mascot.happy();
    const destinations = { student: "student.html", driver: "driver.html", admin: "admin.html" };
    setTimeout(() => {
      navigateTo(destinations[data.user.role] || "admin.html", 260);
    }, 500);
  } catch (err) {
    submitBtn.classList.remove("loading");
    mascot.sad();
    errorBox.textContent = "Could not reach the server. Is the Flask backend running?";
    errorBox.style.display = "block";
  }
});
