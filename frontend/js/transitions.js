/**
 * Fades the page out before any internal navigation (clicking a plain link,
 * or a script-driven redirect via navigateTo()) so moving between pages
 * feels like one continuous app instead of a hard page reload. Pairs with
 * the page-fade-in animation already applied to <body> in style.css.
 */
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[href]");
  if (!a || a.target === "_blank" || e.metaKey || e.ctrlKey || e.shiftKey || a.hasAttribute("download")) return;

  let url;
  try {
    url = new URL(a.href, window.location.href);
  } catch (err) {
    return;
  }
  if (url.origin !== window.location.origin) return;

  e.preventDefault();
  document.body.classList.add("page-transition-out");
  setTimeout(() => { window.location.href = a.href; }, 220);
});

function navigateTo(url, delay = 220) {
  document.body.classList.add("page-transition-out");
  setTimeout(() => { window.location.href = url; }, delay);
}
