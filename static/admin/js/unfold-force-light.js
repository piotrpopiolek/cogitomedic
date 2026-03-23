(function () {
  document.documentElement.classList.remove("dark");
  document.documentElement.setAttribute("data-theme", "light");
  document.documentElement.setAttribute("data-color-scheme", "light");
  try {
    localStorage.setItem("theme", "light");
    localStorage.setItem("unfold.theme", "light");
    localStorage.setItem("color-theme", "light");
  } catch (e) {}
})();
