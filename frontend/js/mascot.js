/**
 * The little bus-driver mascot on the login/signup pages: eyes track what
 * you type in the username field, hands cover his eyes while you type a
 * password, and he reacts (frown+shake / big smile+wave) to login results.
 */
function initMascot({ usernameInput, passwordInput } = {}) {
  const wrap = document.querySelector(".mascot-wrap");
  if (!wrap) return { sad() {}, happy() {} };

  const pupilL = document.getElementById("pupil-l");
  const pupilR = document.getElementById("pupil-r");
  const mouth = document.getElementById("mascot-mouth");
  const card = wrap.closest(".login-card") || wrap;

  const SMILE = "M82,128 Q100,140 118,128";
  const FROWN = "M82,136 Q100,124 118,136";
  const BIG_SMILE = "M76,124 Q100,150 124,124";

  function lookAt(x, y) {
    const t = `translate(${x}px, ${y}px)`;
    if (pupilL) pupilL.style.transform = t;
    if (pupilR) pupilR.style.transform = t;
  }

  function setMouth(d) {
    if (mouth) mouth.setAttribute("d", d);
  }

  if (usernameInput) {
    usernameInput.addEventListener("focus", () => lookAt(0, 3));
    usernameInput.addEventListener("input", () => {
      const len = usernameInput.value.length;
      const shift = ((len % 14) - 7) * 1.1;
      lookAt(shift, 3);
    });
    usernameInput.addEventListener("blur", () => lookAt(0, 0));
  }

  if (passwordInput) {
    passwordInput.addEventListener("focus", () => wrap.classList.add("peeking"));
    passwordInput.addEventListener("blur", () => wrap.classList.remove("peeking"));
  }

  function sad() {
    card.classList.add("shake");
    setMouth(FROWN);
    setTimeout(() => {
      card.classList.remove("shake");
      setMouth(SMILE);
    }, 1300);
  }

  function happy() {
    wrap.classList.add("wave");
    setMouth(BIG_SMILE);
    setTimeout(() => wrap.classList.remove("wave"), 850);
  }

  return { sad, happy };
}
