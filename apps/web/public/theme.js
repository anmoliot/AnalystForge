(() => {
  const stored = localStorage.getItem("af-theme");
  const theme =
    stored === "light" || stored === "dark"
      ? stored
      : window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark";
  document.documentElement.dataset.theme = theme;
})();
